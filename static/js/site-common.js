(() => {
    const scrollItems = document.querySelectorAll('.animate-on-scroll');

    if (scrollItems.length) {
        const scrollObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.2 });

        scrollItems.forEach(item => scrollObserver.observe(item));
    }

    const zoomModal = document.getElementById('zoom-modal');
    const zoomImage = document.getElementById('zoom-image');

    if (!zoomModal || !zoomImage) {
        return;
    }

    document.querySelectorAll('.flake-card img, .flakes-popular-card img').forEach(image => {
        image.addEventListener('click', () => {
            zoomImage.src = image.src;
            zoomImage.alt = image.alt || 'Zoomed image';
            zoomModal.style.display = 'flex';

            requestAnimationFrame(() => {
                zoomModal.classList.add('show');
            });
        });
    });

    zoomModal.addEventListener('click', () => {
        zoomModal.classList.remove('show');
        setTimeout(() => {
            zoomModal.style.display = 'none';
        }, 300);
    });
})();
