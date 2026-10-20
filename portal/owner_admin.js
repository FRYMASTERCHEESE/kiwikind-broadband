'use strict';
window.kiwiKindOwnerSignIn = async function (response) {
  const error = document.getElementById('owner-error');
  const form = document.getElementById('owner-google-form');
  error.textContent = 'Checking your Google account…';
  try {
    const body = new URLSearchParams(new FormData(form));
    body.set('credential', response.credential);
    const result = await fetch(form.action, {
      method: 'POST', credentials: 'same-origin', body,
      headers: {'X-CSRFToken': body.get('csrfmiddlewaretoken')}
    });
    const data = await result.json();
    if (result.ok && data.redirect === '/admin/mfa/') window.location.assign('/admin/mfa/');
    else error.textContent = data.error || 'Sign-in failed. Reload this page and try again.';
  } catch (_) {
    error.textContent = 'Could not connect. Reload this page and try again.';
  }
};
