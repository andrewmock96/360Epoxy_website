(() => {
    const menuToggle = document.querySelector('.menu-toggle');
    const mobileNav = document.querySelector('.mobile-nav');

    if (!menuToggle || !mobileNav) {
        return;
    }

    menuToggle.addEventListener('click', () => {
        mobileNav.classList.toggle('active');
        menuToggle.setAttribute('aria-expanded', mobileNav.classList.contains('active'));
    });

    mobileNav.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            mobileNav.classList.remove('active');
            menuToggle.setAttribute('aria-expanded', 'false');
        });
    });
})();
