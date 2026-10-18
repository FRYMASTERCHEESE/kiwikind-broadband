'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('ticket_form');
  if (!form) return;
  let saving = false;
  form.addEventListener('submit', event => {
    if (saving) { event.preventDefault(); return; }
    saving = true;
    const clicked = event.submitter;
    if (clicked && clicked.name) {
      const choice = document.createElement('input');
      choice.type = 'hidden'; choice.name = clicked.name; choice.value = clicked.value;
      form.append(choice);
    }
    form.querySelectorAll('input[type="submit"], button[type="submit"]').forEach(button => {
      button.disabled = true;
      if (button.tagName === 'INPUT') button.value = 'Saving…';
      else button.textContent = 'Saving…';
    });
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
});
