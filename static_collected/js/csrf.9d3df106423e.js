function getCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

// Wraps fetch() so every non-GET request carries the CSRF header Django's
// CsrfViewMiddleware requires for session-authenticated POSTs. The
// csrftoken cookie is set automatically because every page renders at
// least one {% csrf_token %} form.
function apiFetch(url, options) {
  options = options || {};
  options.headers = options.headers || {};
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    options.headers['X-CSRFToken'] = getCookie('csrftoken');
  }
  options.credentials = 'same-origin';
  return fetch(url, options);
}
