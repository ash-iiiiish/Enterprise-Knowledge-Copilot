"""Business rules for assigning tasks, notifying people and who may do what."""
from datetime import timedelta

import pytest

from core.timeutil import today_local
from tests.conftest import needs_db

pytestmark = needs_db


async def _unread(user):
    from db.task_repository import list_notifications

    return (await list_notifications(user.id))["items"]


async def test_hr_assigns_and_assignee_is_notified(people):
    from db.task_repository import assign_tasks

    res = await assign_tasks(people.hr, title="Q3 report", assignees=[people.eng1.employee_id], priority="high", due_date=today_local() + timedelta(days=2))
    assert res["count"] == 1 and res["tasks"][0]["assigned_to"]["id"] == people.eng1.id
    inbox = await _unread(people.eng1)
    assert inbox and inbox[0]["kind"] == "task_assigned" and "Q3 report" in inbox[0]["body"]
    assert await _unread(people.hr) == []  # assigner isn't spammed


async def test_assign_by_fuzzy_name_and_typo(people):
    from db.task_repository import assign_tasks

    r1 = await assign_tasks(people.hr, title="A", assignees=[f"priya {people.tag}"])
    assert r1["tasks"][0]["assigned_to"]["id"] == people.eng1.id
    r2 = await assign_tasks(people.hr, title="B", assignees=[f"Priyaa {people.tag}"])  # typo tolerated
    assert r2["tasks"][0]["assigned_to"]["id"] == people.eng1.id


async def test_department_broadcast_and_everyone(people):
    from db.task_repository import TaskError, assign_tasks

    dept = people.mgr.department
    res = await assign_tasks(people.mgr, title="Sprint review", department=dept)  # manager -> own team
    assert {t["assigned_to"]["id"] for t in res["tasks"]} == {people.mgr.id, people.eng1.id, people.eng2.id}
    with pytest.raises(TaskError):
        await assign_tasks(people.mgr, title="x", department="everyone")  # company-wide is HR only
    with pytest.raises(TaskError):
        await assign_tasks(people.mgr, title="x", department=people.des.department)  # not their team
    everyone = await assign_tasks(people.hr, title="Security training", department="everyone")
    assert everyone["count"] >= 5


async def test_employee_cannot_assign_to_others_but_can_self_assign(people):
    from db.task_repository import TaskError, assign_tasks

    with pytest.raises(TaskError):
        await assign_tasks(people.eng1, title="x", assignees=[people.eng2.employee_id])
    with pytest.raises(TaskError):
        await assign_tasks(people.eng1, title="x", department=people.eng1.department)
    mine = await assign_tasks(people.eng1, title="Remind me", assignees=["me"])
    assert mine["tasks"][0]["assigned_to"]["id"] == people.eng1.id
    assert await _unread(people.eng1) == []  # no notification for your own task


async def test_ambiguous_and_unknown_people_create_nothing(people):
    from db.task_repository import TaskError, assign_tasks, query_tasks

    with pytest.raises(TaskError, match="ambiguous|Did you mean"):
        await assign_tasks(people.hr, title="x", assignees=[people.tag])  # matches several people? tag is in every name
    with pytest.raises(TaskError, match="couldn't find"):
        await assign_tasks(people.hr, title="x", assignees=["Zzyzx Nobody"])
    assert await query_tasks(people.hr, scope="assigned_by_me") == []


async def test_past_due_date_rejected(people):
    from db.task_repository import TaskError, assign_tasks

    with pytest.raises(TaskError, match="past"):
        await assign_tasks(people.hr, title="x", assignees=[people.eng1.employee_id], due_date=today_local() - timedelta(days=1))


async def test_status_flow_notifies_creator(people):
    from db.task_repository import assign_tasks, update_task

    t = (await assign_tasks(people.hr, title="Ship it", assignees=[people.eng1.employee_id]))["tasks"][0]
    res = await update_task(people.eng1, t["id"], status="done")
    assert res["task"]["status"] == "done" and res["task"]["completed_at"]
    inbox = await _unread(people.hr)
    assert inbox[0]["kind"] == "task_done" and people.eng1.name in inbox[0]["title"]
    reopened = await update_task(people.eng1, t["id"], status="todo")
    assert reopened["task"]["completed_at"] is None


async def test_update_permissions(people):
    from db.task_repository import TaskError, assign_tasks, update_task

    t = (await assign_tasks(people.hr, title="Locked", assignees=[people.eng1.employee_id]))["tasks"][0]
    with pytest.raises(TaskError):  # bystander
        await update_task(people.eng2, t["id"], status="done")
    with pytest.raises(TaskError):  # assignee can't change details, only status
        await update_task(people.eng1, t["id"], priority="low")
    moved = await update_task(people.hr, t["id"], due_date=today_local() + timedelta(days=5), reassign_to=people.eng2.employee_id)
    assert moved["task"]["assigned_to"]["id"] == people.eng2.id
    assert (await _unread(people.eng2))[0]["kind"] == "task_assigned"


async def test_visibility_and_filters(people):
    from db.task_repository import assign_tasks, query_tasks

    a = (await assign_tasks(people.hr, title="Visible to Priya", assignees=[people.eng1.employee_id], priority="urgent"))["tasks"][0]
    await assign_tasks(people.hr, title="Only Pavan", assignees=[people.eng2.employee_id])
    mine = await query_tasks(people.eng1)
    assert [t["id"] for t in mine] == [a["id"]]
    assert await query_tasks(people.eng2, assigned_to=people.eng1.employee_id) == []  # can't peek at others' tasks
    assert len(await query_tasks(people.hr, scope="all", priority="urgent", assigned_to=people.eng1.employee_id)) == 1
    assert len(await query_tasks(people.hr, scope="assigned_by_me")) == 2


async def test_due_reminders_sent_once(people):
    from db.task_repository import assign_tasks, send_due_reminders

    await assign_tasks(people.hr, title="Due tomorrow", assignees=[people.eng1.employee_id], due_date=today_local() + timedelta(days=1))
    await send_due_reminders()
    first = [n for n in await _unread(people.eng1) if n["kind"] == "reminder"]
    assert len(first) == 1
    await send_due_reminders()
    assert len([n for n in await _unread(people.eng1) if n["kind"] == "reminder"]) == 1  # not repeated within 20h
