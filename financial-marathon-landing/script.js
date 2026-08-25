// Mobile navigation toggle
const burger = document.getElementById('burger');
const mainNav = document.getElementById('main-nav');

if (burger && mainNav) {
  burger.addEventListener('click', () => {
    const isOpen = mainNav.classList.toggle('is-open');
    burger.setAttribute('aria-expanded', String(isOpen));
  });

  mainNav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      mainNav.classList.remove('is-open');
      burger.setAttribute('aria-expanded', 'false');
    });
  });
}

// Scroll reveal animation
const revealItems = document.querySelectorAll('.reveal');

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

  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('is-visible'));
}

// Signup form handling.
// NOTE: there is no backend wired up yet — this only validates the fields
// and swaps in a success state. Replace the block inside the submit
// handler with a real request to your CRM / email service before launch.
const form = document.getElementById('signup-form');
const successState = document.getElementById('signup-success');

if (form && successState) {
  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const nameInput = document.getElementById('name');
    const emailInput = document.getElementById('email');
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    let isValid = true;

    if (!nameInput.value.trim()) {
      nameInput.classList.add('is-invalid');
      isValid = false;
    } else {
      nameInput.classList.remove('is-invalid');
    }

    if (!emailPattern.test(emailInput.value.trim())) {
      emailInput.classList.add('is-invalid');
      isValid = false;
    } else {
      emailInput.classList.remove('is-invalid');
    }

    if (!isValid) return;

    // TODO: send { name, email } to your actual signup endpoint here.
    form.hidden = true;
    successState.hidden = false;
  });
}
