// Original SVG illustrations (glossy "3D-ish" look built from gradients).
// Every function takes a unique id so gradients don't collide when reused.

export const robot = (id = "r") => `
<svg viewBox="0 0 420 470" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Friendly robot assistant" class="robot">
  <defs>
    <radialGradient id="${id}-ball" cx="35%" cy="30%" r="75%"><stop offset="0" stop-color="#a9c4ff"/><stop offset="1" stop-color="#2f6bff"/></radialGradient>
    <linearGradient id="${id}-head" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#eceffd"/><stop offset="1" stop-color="#cdd5f6"/></linearGradient>
    <linearGradient id="${id}-ear" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4f6ff"/><stop offset="1" stop-color="#bfc9f3"/></linearGradient>
    <linearGradient id="${id}-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6c9bff"/><stop offset="1" stop-color="#1d4fe0"/></linearGradient>
    <linearGradient id="${id}-screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#555861"/><stop offset=".45" stop-color="#1c1d23"/><stop offset="1" stop-color="#08080b"/></linearGradient>
    <linearGradient id="${id}-base" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7ca5ff"/><stop offset="1" stop-color="#2458e8"/></linearGradient>
    <filter id="${id}-sh" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="20" stdDeviation="18" flood-color="#2f6bff" flood-opacity=".25"/></filter>
  </defs>
  <ellipse cx="210" cy="440" rx="130" ry="14" fill="#2f6bff" opacity=".12"/>
  <g class="robot-float">
    <rect x="203" y="54" width="14" height="62" rx="7" fill="#cdd6ff"/>
    <circle cx="210" cy="40" r="27" fill="url(#${id}-ball)"/>
    <ellipse cx="200" cy="29" rx="9" ry="5.5" fill="#fff" opacity=".6"/>
    <rect x="20" y="172" width="76" height="152" rx="38" fill="url(#${id}-ear)"/>
    <rect x="324" y="172" width="76" height="152" rx="38" fill="url(#${id}-ear)"/>
    <rect x="30" y="204" width="13" height="92" rx="6.5" fill="#3f78ff" opacity=".75"/>
    <rect x="377" y="204" width="13" height="92" rx="6.5" fill="#3f78ff" opacity=".75"/>
    <rect x="60" y="100" width="300" height="252" rx="122" fill="url(#${id}-head)" filter="url(#${id}-sh)"/>
    <rect x="88" y="128" width="244" height="198" rx="94" fill="url(#${id}-rim)"/>
    <rect x="102" y="142" width="216" height="170" rx="82" fill="url(#${id}-screen)"/>
    <ellipse cx="170" cy="170" rx="70" ry="18" fill="#fff" opacity=".1" transform="rotate(-14 170 170)"/>
    <g class="robot-eyes"><ellipse cx="170" cy="224" rx="21" ry="26" fill="#fff"/><ellipse cx="250" cy="224" rx="21" ry="26" fill="#fff"/></g>
    <rect x="192" y="270" width="36" height="13" rx="6.5" fill="#fff"/>
    <ellipse cx="210" cy="372" rx="124" ry="28" fill="url(#${id}-base)"/>
    <ellipse cx="210" cy="362" rx="100" ry="17" fill="#9dbbff" opacity=".55"/>
  </g>
</svg>`;

export const logoMark = (id = "lm") => `
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="${id}-a" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#cdd5f6"/></linearGradient>
    <linearGradient id="${id}-b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6c9bff"/><stop offset="1" stop-color="#1d4fe0"/></linearGradient>
  </defs>
  <rect x="3" y="15" width="6" height="14" rx="3" fill="#bfc9f3"/><rect x="39" y="15" width="6" height="14" rx="3" fill="#bfc9f3"/>
  <rect x="7" y="10" width="34" height="30" rx="13" fill="url(#${id}-a)" stroke="#d6dcf7" stroke-width="1"/>
  <rect x="11" y="14.5" width="26" height="21" rx="9.5" fill="url(#${id}-b)"/>
  <rect x="13" y="16.5" width="22" height="17" rx="8" fill="#16171c"/>
  <circle cx="19.5" cy="25" r="2.6" fill="#fff"/><circle cx="28.5" cy="25" r="2.6" fill="#fff"/>
  <rect x="23" y="4" width="2.4" height="7" rx="1.2" fill="#b7c4f5"/><circle cx="24.2" cy="4" r="3.4" fill="#2f6bff"/>
  <circle cx="40" cy="9" r="5" fill="#5b8dff"/><circle cx="38" cy="9" r="1" fill="#fff"/><circle cx="40" cy="9" r="1" fill="#fff"/><circle cx="42" cy="9" r="1" fill="#fff"/>
</svg>`;

export const plane = (id = "pl") => `
<svg viewBox="0 0 330 270" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="${id}-1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2f6bff"/><stop offset="1" stop-color="#7aa2ff"/></linearGradient>
    <linearGradient id="${id}-2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a9c2ff"/><stop offset="1" stop-color="#e9f0ff"/></linearGradient>
    <linearGradient id="${id}-3" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1a47c8"/><stop offset="1" stop-color="#3d74ff"/></linearGradient>
  </defs>
  <polygon points="12,104 318,8 128,150" fill="url(#${id}-1)"/>
  <polygon points="128,150 318,8 156,248" fill="url(#${id}-2)"/>
  <polygon points="128,150 156,248 176,176" fill="url(#${id}-3)"/>
  <polygon points="128,150 176,176 318,8" fill="#6f98ff" opacity=".55"/>
  <rect x="14" y="196" width="78" height="12" rx="6" fill="#dfe3ec" transform="rotate(-30 14 196)"/>
  <rect x="40" y="232" width="62" height="12" rx="6" fill="#dfe3ec" transform="rotate(-30 40 232)"/>
</svg>`;

export const bubble = (id = "bb") => `
<svg viewBox="0 0 200 190" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <radialGradient id="${id}-g" cx="30%" cy="25%" r="85%"><stop offset="0" stop-color="#8db0ff"/><stop offset=".55" stop-color="#3a74ff"/><stop offset="1" stop-color="#1d4fe0"/></radialGradient>
  </defs>
  <path d="M100 8c50 0 92 30 92 72s-42 72-92 72c-9 0-18-1-26-3l-40 30 10-40C18 126 8 104 8 80 8 38 50 8 100 8z" fill="url(#${id}-g)"/>
  <ellipse cx="70" cy="40" rx="36" ry="14" fill="#fff" opacity=".28" transform="rotate(-18 70 40)"/>
  <circle cx="64" cy="82" r="11" fill="#fff"/><circle cx="100" cy="82" r="11" fill="#fff"/><circle cx="136" cy="82" r="11" fill="#fff"/>
</svg>`;
