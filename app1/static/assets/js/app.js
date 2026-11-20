/* Scholarship Spy: small progressive enhancements. Everything still works without JavaScript. */
(function () {
  // Save/unsave scholarships without reloading the page.
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form.classList || !form.classList.contains('save-form') || !window.fetch) return;
    event.preventDefault();
    var button = form.querySelector('button');
    button.disabled = true;
    fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw r; return r.json(); })
      .then(function (data) {
        var label = button.querySelector('span');
        button.classList.toggle('is-saved', data.saved);
        button.setAttribute('aria-pressed', data.saved);
        button.title = data.saved ? 'Remove from my applications' : 'Save to my applications';
        button.querySelector('i').className = data.saved ? 'bi bi-bookmark-fill' : 'bi bi-bookmark';
        if (label) label.textContent = data.saved ? 'Saved' : 'Save';
      })
      .catch(function () { form.submit(); })  // fall back to a normal post
      .finally(function () { button.disabled = false; });
  });
})();
