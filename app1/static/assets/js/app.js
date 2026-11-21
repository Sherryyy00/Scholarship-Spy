/* Scholarship Spy: small progressive enhancements. Everything still works without JavaScript.
   All page scripts live here (no inline <script> or on* attributes), so the
   Content-Security-Policy can allow scripts from this site only. */
(function () {
  function post(form) {
    return fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw r; return r; });
  }

  // Save/unsave scholarships without reloading; confirm before destructive forms.
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (form.dataset && form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
      return;
    }
    if (!form.classList || !form.classList.contains('save-form') || !window.fetch) return;
    event.preventDefault();
    var button = form.querySelector('button');
    button.disabled = true;
    post(form)
      .then(function (r) { return r.json(); })
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

  // Mobile menu: keep the button's label in sync, lock page scroll, close on link tap or Escape.
  // (main.js toggles the menu itself.)
  var navToggle = document.querySelector('.mobile-nav-toggle');
  var navbar = document.getElementById('navbar');
  if (navToggle && navbar) {
    var sync = function () {
      var open = navbar.classList.contains('navbar-mobile');
      navToggle.setAttribute('aria-expanded', open);
      navToggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      document.body.classList.toggle('nav-open', open);
    };
    navToggle.addEventListener('click', function () { setTimeout(sync, 0); });
    var close = function () {
      if (!navbar.classList.contains('navbar-mobile')) return;
      navbar.classList.remove('navbar-mobile');
      navToggle.classList.add('bi-list'); navToggle.classList.remove('bi-x');
      sync();
    };
    navbar.addEventListener('click', function (e) {
      if (e.target === navbar || e.target.closest('ul a')) close();  // backdrop or a link
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  }

  // Controls that submit their form as soon as they change (sort, "eligible only").
  document.querySelectorAll('.js-autosubmit').forEach(function (el) {
    el.addEventListener('change', function () { el.form.submit(); });
  });

  // Application status: post in the background, then refresh.
  document.querySelectorAll('.js-autosave').forEach(function (select) {
    select.addEventListener('change', function () {
      var form = select.form;
      post(form).then(function () { window.location.reload(); }).catch(function () { form.submit(); });
    });
  });

  // Home page search fields: highlight while in use.
  document.querySelectorAll('.styled-input.multi input').forEach(function (input) {
    var box = input.parentElement && input.parentElement.parentElement;
    input.addEventListener('focus', function () { box && box.classList.add('active'); });
    input.addEventListener('blur', function () {
      box && box.classList.remove('active');
      input.setAttribute('filled', input.value ? 'true' : 'false');
    });
  });

  // Recommendations form: statement / CV tabs, file name, character counter, busy button.
  var recForm = document.getElementById('rec-form');
  if (recForm) {
    var choices = document.querySelectorAll('.input-choice .choice');
    choices.forEach(function (btn) {
      btn.addEventListener('click', function () {
        choices.forEach(function (b) {
          var on = b === btn;
          b.classList.toggle('active', on);
          b.setAttribute('aria-selected', on);
          document.getElementById(b.dataset.target).hidden = !on;
        });
      });
    });
    var cv = document.getElementById('id_cv');
    if (cv) cv.addEventListener('change', function () {
      document.getElementById('cv-name').textContent = cv.files.length ? cv.files[0].name : 'Choose your CV';
    });
    var text = document.getElementById('id_statement');
    var counter = document.getElementById('char-count');
    var min = parseInt(recForm.dataset.minLength, 10) || 0;
    function update() {
      var n = text.value.trim().length;
      counter.textContent = n ? n + ' / ' + min + (n >= min ? ' ✓' : '') : '';
    }
    if (text && counter) { text.addEventListener('input', update); update(); }
    recForm.addEventListener('submit', function () {
      var btn = document.getElementById('rec-submit');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Finding matches…';
    });
    if (recForm.dataset.mode === 'cv' && choices[1]) choices[1].click();  // reopen CV tab after a failed upload
  }
})();
