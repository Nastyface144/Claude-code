(() => {
  'use strict';

  document.documentElement.classList.add('has-js');

  // ---- header: solid background after scroll ----
  const header = document.querySelector('.site-header');

  if (header) {
    const onScroll = () => {
      header.classList.toggle('is-scrolled', window.scrollY > 40);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

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

  // ---- hero booking card: subtle tilt on mouse move ----
  const bookingCard = document.getElementById('booking-card');
  const heroVisual = document.querySelector('.hero-visual');

  if (bookingCard && heroVisual && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    heroVisual.addEventListener('mousemove', (e) => {
      const rect = heroVisual.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      bookingCard.style.transform = `rotateY(${x * 6}deg) rotateX(${y * -6}deg)`;
    });

    heroVisual.addEventListener('mouseleave', () => {
      bookingCard.style.transform = 'rotateY(0) rotateX(0)';
    });
  }

  // ---- hero booking mock: light interactivity ----
  document.querySelectorAll('.booking-chips, .booking-days, .booking-slots').forEach((group) => {
    group.querySelectorAll('span').forEach((item) => {
      item.addEventListener('click', () => {
        group.querySelectorAll('span').forEach((el) => {
          el.classList.remove('chip--active', 'day--active', 'slot--active');
        });
        if (group.classList.contains('booking-chips')) item.classList.add('chip--active');
        if (group.classList.contains('booking-days')) item.classList.add('day--active');
        if (group.classList.contains('booking-slots')) item.classList.add('slot--active');
      });
    });
  });

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
    const submitBtn = form.querySelector('button[type="submit"]');
    const defaultBtnText = submitBtn ? submitBtn.textContent : '';

    form.addEventListener('submit', (event) => {
      event.preventDefault();

      const name = form.querySelector('#cta-name').value.trim();
      const phone = form.querySelector('#cta-phone').value.trim();
      if (!name || !phone) return;

      note.textContent = `Спасибо, ${name}! Перезвоним на ${phone} в течение дня, чтобы согласовать время.`;
      note.style.color = 'var(--choc)';
      form.reset();
      if (submitBtn) submitBtn.textContent = 'Заявка отправлена ✓';

      setTimeout(() => {
        note.textContent = defaultNote;
        note.style.color = '';
        if (submitBtn) submitBtn.textContent = defaultBtnText;
      }, 5000);
    });
  }
})();
