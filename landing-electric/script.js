(() => {
  'use strict';

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

  // ---- phone mask ----
  const phoneInput = document.getElementById('phone');

  if (phoneInput) {
    phoneInput.addEventListener('input', () => {
      let digits = phoneInput.value.replace(/\D/g, '').replace(/^7|^8/, '');
      digits = digits.slice(0, 10);

      let formatted = '+7';
      if (digits.length > 0) formatted += ' (' + digits.slice(0, 3);
      if (digits.length >= 3) formatted += ') ' + digits.slice(3, 6);
      if (digits.length >= 6) formatted += '-' + digits.slice(6, 8);
      if (digits.length >= 8) formatted += '-' + digits.slice(8, 10);

      phoneInput.value = formatted;
    });
  }

  // ---- final CTA form (front-end only demo) ----
  const form = document.getElementById('cta-form');
  const note = document.getElementById('cta-note');

  if (form && note) {
    const defaultNote = note.textContent;

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const phone = form.querySelector('#phone').value.trim();
      if (!phone) return;

      note.textContent = `Заявка принята — перезвоним на ${phone} в течение 15 минут.`;
      note.style.color = 'var(--amber)';
      form.querySelector('input').value = '';
      form.querySelector('button').textContent = 'Заявка отправлена ✓';

      setTimeout(() => {
        note.textContent = defaultNote;
        note.style.color = '';
        form.querySelector('button').textContent = 'Заказать бесплатный замер';
      }, 4000);
    });
  }
})();
