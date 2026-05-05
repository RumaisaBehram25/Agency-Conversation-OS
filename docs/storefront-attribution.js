/*
 * Attora — Storefront Attribution Bridge
 *
 * Drop this <script> into the <head> of the product page (and ideally every
 * page in the funnel up to the thank-you page). It captures the Attora
 * attribution params from the URL on landing, persists them in localStorage,
 * and re-appends them to every checkout/buy link on the page so they survive
 * the redirect into the checkout flow.
 *
 * Params tracked: attora_sub, attora_id, utm_source, utm_medium,
 * utm_campaign, utm_content, utm_term.
 *
 * The final checkout / thank-you page should still POST these to
 * /api/conversions/track on the Attora backend so the conversion is recorded.
 */
(function () {
  var STORAGE_KEY = 'attora_attribution';
  var TRACKED = [
    'attora_sub',
    'attora_id',
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_content',
    'utm_term',
  ];
  var TTL_DAYS = 30;

  // 1. Capture from current URL and stash in localStorage.
  try {
    var url = new URL(window.location.href);
    var captured = {};
    TRACKED.forEach(function (p) {
      var v = url.searchParams.get(p);
      if (v) captured[p] = v;
    });
    if (Object.keys(captured).length) {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ params: captured, savedAt: Date.now() })
      );
    }
  } catch (e) { /* private mode / disabled storage — silently skip */ }

  // 2. Read back, honouring TTL.
  function getStoredParams() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      var ageDays = (Date.now() - parsed.savedAt) / 86400000;
      if (ageDays > TTL_DAYS) {
        localStorage.removeItem(STORAGE_KEY);
        return {};
      }
      return parsed.params || {};
    } catch (e) {
      return {};
    }
  }

  // 3. Append stored params to a URL without overwriting params already on it.
  function stamp(href) {
    var stored = getStoredParams();
    var keys = Object.keys(stored);
    if (!keys.length) return href;
    try {
      var u = new URL(href, window.location.href);
      keys.forEach(function (k) {
        if (!u.searchParams.has(k)) u.searchParams.set(k, stored[k]);
      });
      return u.toString();
    } catch (e) {
      return href;
    }
  }

  // 4. Rewrite every <a href> on the page (skip mailto/tel/js/anchors).
  function processLinks() {
    var anchors = document.querySelectorAll('a[href]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      var href = a.getAttribute('href');
      if (!href || /^(mailto:|tel:|javascript:|#)/i.test(href)) continue;
      var stamped = stamp(href);
      if (stamped !== href) a.setAttribute('href', stamped);
    }
  }

  processLinks();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', processLinks);
  }

  // 5. Catch dynamically-added links (SPA cart widgets, popup checkouts).
  if (window.MutationObserver) {
    var mo = new MutationObserver(processLinks);
    var start = function () {
      mo.observe(document.body, { childList: true, subtree: true });
    };
    if (document.body) start();
    else document.addEventListener('DOMContentLoaded', start);
  }

  // 6. Catch <form> POSTs (e.g. Shopify "Add to cart" forms) by injecting
  //    hidden inputs so the params land in the cart's note attributes.
  document.addEventListener(
    'submit',
    function (ev) {
      var form = ev.target;
      if (!form || form.tagName !== 'FORM') return;
      var stored = getStoredParams();
      Object.keys(stored).forEach(function (k) {
        if (form.querySelector('input[name="' + k + '"]')) return;
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = k;
        input.value = stored[k];
        form.appendChild(input);
      });
    },
    true
  );
})();
