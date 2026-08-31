(() => {
  'use strict';

  // ---- mobile nav ----
  const burger = document.getElementById('burger');
  const header = document.querySelector('.site-header');

  if (burger && header) {
    burger.addEventListener('click', () => {
      const isOpen = header.classList.toggle('is-open');
      burger.classList.toggle('is-open', isOpen);
      burger.setAttribute('aria-expanded', String(isOpen));
    });

    header.querySelectorAll('.main-nav a').forEach((link) => {
      link.addEventListener('click', () => {
        header.classList.remove('is-open');
        burger.classList.remove('is-open');
        burger.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // ---- scroll progress bar ----
  const progress = document.getElementById('scroll-progress');

  if (progress) {
    const updateProgress = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = scrollable > 0 ? window.scrollY / scrollable : 0;
      progress.style.width = `${Math.min(1, Math.max(0, ratio)) * 100}%`;
    };

    updateProgress();
    window.addEventListener('scroll', updateProgress, { passive: true });
    window.addEventListener('resize', updateProgress);
  }

  // ---- live UTC clock ----
  const clock = document.getElementById('clock');

  if (clock) {
    const tick = () => {
      const now = new Date();
      const hh = String(now.getUTCHours()).padStart(2, '0');
      const mm = String(now.getUTCMinutes()).padStart(2, '0');
      const ss = String(now.getUTCSeconds()).padStart(2, '0');
      clock.textContent = `UTC ${hh}:${mm}:${ss}`;
    };

    tick();
    setInterval(tick, 1000);
  }

  // ---- pricing period switch ----
  const periodCheckbox = document.getElementById('period-checkbox');
  const tagCards = document.querySelectorAll('.tag-card');

  if (periodCheckbox) {
    periodCheckbox.addEventListener('change', () => {
      tagCards.forEach((card) => {
        card.classList.toggle('show-yearly', periodCheckbox.checked);
      });
    });
  }

  // ---- FAQ grep filter ----
  const faqInput = document.getElementById('faq-input');
  const faqPairs = document.querySelectorAll('.faq-pair');
  const faqEmpty = document.getElementById('faq-empty');

  if (faqInput) {
    faqInput.addEventListener('input', () => {
      const query = faqInput.value.trim().toLowerCase();
      let visibleCount = 0;

      faqPairs.forEach((pair) => {
        const haystack = pair.dataset.text || '';
        const matches = query === '' || haystack.includes(query);
        pair.hidden = !matches;
        if (matches) visibleCount += 1;
      });

      if (faqEmpty) faqEmpty.hidden = visibleCount !== 0;
    });
  }
})();
