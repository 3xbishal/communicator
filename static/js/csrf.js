function getCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

function csrfSafeMethod(method) {
  return /^(GET|HEAD|OPTIONS|TRACE)$/.test(method);
}

// Standard Django + jQuery pattern: every non-GET $.ajax()/$.post() call
// across the app automatically carries the CSRF header Django's
// CsrfViewMiddleware requires, without each caller having to remember to
// add it. The csrftoken cookie is set automatically because every page
// renders at least one {% csrf_token %} form.
$.ajaxSetup({
  beforeSend: function (xhr, settings) {
    if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
      xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
    }
  },
});
