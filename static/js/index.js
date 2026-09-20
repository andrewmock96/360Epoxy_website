document.querySelectorAll('.flake-img').forEach(image => {
    image.addEventListener('click', () => {
        const modal = document.getElementById('flakeModal');
        const modalImage = document.getElementById('flakeModalImg');

        if (!modal || !modalImage) {
            return;
        }

        modal.style.display = 'block';
        modalImage.src = image.src;
    });
});

const flakeClose = document.querySelector('.flake-close');
if (flakeClose) {
    flakeClose.addEventListener('click', () => {
        const modal = document.getElementById('flakeModal');
        if (modal) {
            modal.style.display = 'none';
        }
    });
}
