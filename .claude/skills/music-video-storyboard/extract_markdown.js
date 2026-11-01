() => {
  // Pass the ENTIRE contents of this file to browser_evaluate (it is one
  // complete arrow-function expression).
  // It serializes the 1st response (the first model turn with substantive
  // answer text — the H3 storyboard) into clean markdown. The Thoughts panel is
  // reasoning, not a response.
  const turns = [...document.querySelectorAll('ms-chat-turn')];

  // The pipeline extracts the FIRST substantive model response. That is the
  // Film Director storyboard. Any later response is ignored.
  //
  // Distinction that matters: the collapsible "Thoughts" panel is NOT a
  // response. It is internal reasoning rendered directly above the answer
  // (visually under the same "Model • time" header), and in the DOM it is its
  // own ms-chat-turn containing zero answer text. It must never be counted as
  // response #1 — doing so mislabels the real storyboard as "response #2".
  // The 1st response is the first model turn whose answer content
  // (ms-text-chunk ms-cmark-node.cmark-node) is substantive (>200 chars).
  //
  // Do not fall back to a later response. If no substantive answer turn exists
  // yet, return '' and let the caller wait; if the 1st response is genuinely
  // wrong or empty, REFRESH THE PAGE and rerun the flow.
  const modelTurns = turns.filter((t) => {
    if (!t.querySelector('.chat-turn-container.model')) return false;
    const r = t.querySelector('ms-text-chunk ms-cmark-node.cmark-node');
    const txt = r ? (r.innerText || '').trim() : '';
    return txt.length > 200 && !/^Thoughts\b/i.test(txt);
  });
  if (modelTurns.length < 1) return '';

  const turn = modelTurns[0];
  const root = turn.querySelector('ms-text-chunk ms-cmark-node.cmark-node');
  if (!root || (root.innerText || '').trim().length <= 200) return '';

  // Never extract while the 1st response is still streaming. The Stop button is
  // the in-progress signal; the completion toolbar appears when the turn is done.
  const streaming = [...document.querySelectorAll('button')].some((b) => {
    const label = (
      b.getAttribute('aria-label') || (b.innerText || '').trim()
    ).toLowerCase();
    return label === 'stop' || label.startsWith('stop ');
  });
  if (streaming) return '';

  const listItems = (el) =>
    [...el.querySelectorAll('li')].filter((li) => li.closest('ul,ol') === el);

  const ser = (el) => {
    const tag = el.tagName;
    if (tag === 'H1') return '# ' + el.innerText.trim();
    if (tag === 'H2') return '## ' + el.innerText.trim();
    if (tag === 'H3') return '### ' + el.innerText.trim();
    if (tag === 'H4') return '#### ' + el.innerText.trim();
    if (tag === 'P') return el.innerText.trim();
    if (tag === 'HR') return '---';
    if (tag === 'UL' || tag === 'OL') {
      return listItems(el)
        .map((li, i) => {
          // LI may contain several paragraphs (e.g. Beat / Audio). Keep them
          // indented under the bullet instead of emitting loose paragraphs.
          const parts = li.innerText.split('\n').map((s) => s.trim()).filter(Boolean);
          const bullet = tag === 'OL' ? `${i + 1}. ` : '- ';
          return bullet + parts[0] + parts.slice(1).map((p) => '\n  ' + p).join('');
        })
        .join('\n');
    }
    if (tag === 'BLOCKQUOTE') {
      const items = [];
      const walk = (n) => {
        for (const c of n.children) {
          if (c.tagName === 'P') items.push(c.innerText.trim());
          else if (c.tagName === 'UL' || c.tagName === 'OL') items.push(ser(c));
          else if (c.tagName === 'MS-CMARK-NODE') walk(c);
          else {
            const s = ser(c);
            if (s) items.push(s);
          }
        }
      };
      walk(el);
      return items.join('\n\n').split('\n').map((l) => '> ' + l).join('\n');
    }
    if (tag === 'MS-CODE-BLOCK') {
      const pre = el.querySelector('pre');
      const code = (pre ? pre.textContent : el.innerText).trim();
      return '```text\n' + code + '\n```';
    }
    return [...el.children].map(ser).filter(Boolean).join('\n\n');
  };

  return ser(root);
}
