(() => {
  'use strict';

  // ---- header background on scroll ----
  const header = document.querySelector('.site-header');

  const updateHeader = () => {
    if (!header) return;
    header.classList.toggle('is-scrolled', window.scrollY > 20);
  };
  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });

  // ---- mobile nav ----
  const burger = document.getElementById('burger');
  const nav = document.getElementById('main-nav');

  if (burger && nav) {
    burger.addEventListener('click', () => {
      const isOpen = nav.classList.toggle('is-open');
      burger.classList.toggle('is-open', isOpen);
      burger.setAttribute('aria-expanded', String(isOpen));
    });

    nav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        nav.classList.remove('is-open');
        burger.classList.remove('is-open');
        burger.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // ---- scroll reveal ----
  const revealEls = document.querySelectorAll('.reveal');

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    );

    revealEls.forEach((el) => observer.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add('is-visible'));
  }

  // ---- FAQ accordion ----
  document.querySelectorAll('.faq-question').forEach((btn) => {
    const answer = btn.nextElementSibling;

    btn.addEventListener('click', () => {
      const isOpen = btn.getAttribute('aria-expanded') === 'true';

      document.querySelectorAll('.faq-question').forEach((other) => {
        other.setAttribute('aria-expanded', 'false');
        other.nextElementSibling.style.maxHeight = null;
      });

      if (!isOpen) {
        btn.setAttribute('aria-expanded', 'true');
        answer.style.maxHeight = answer.scrollHeight + 'px';
      }
    });
  });

  // ---- final CTA form (front-end only demo) ----
  const form = document.getElementById('cta-form');
  const note = document.getElementById('cta-note');

  if (form && note) {
    const defaultNote = note.textContent;

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const email = form.querySelector('#email').value.trim();
      if (!email) return;

      note.textContent = `Готово — билет и программа придут на ${email}.`;
      note.style.color = 'var(--teal)';
      form.reset();
      form.querySelector('button').textContent = 'Отправлено ✓';

      setTimeout(() => {
        note.textContent = defaultNote;
        note.style.color = '';
        form.querySelector('button').textContent = 'Купить билет — 12 900 ₽';
      }, 4000);
    });
  }
})();
