(() => {
    const phoneInput = document.getElementById('phone');

    if (!phoneInput) {
        return;
    }

    const formatPhoneNumber = value => {
        let digits = value.replace(/\D/g, '');

        if (digits.length === 11 && digits.startsWith('1')) {
            digits = digits.slice(1);
        }

        digits = digits.slice(0, 10);

        if (digits.length < 4) {
            return digits ? `(${digits}` : '';
        }

        if (digits.length < 7) {
            return `(${digits.slice(0, 3)})-${digits.slice(3)}`;
        }

        return `(${digits.slice(0, 3)})-${digits.slice(3, 6)}-${digits.slice(6)}`;
    };

    phoneInput.value = formatPhoneNumber(phoneInput.value);
    phoneInput.addEventListener('input', event => {
        event.target.value = formatPhoneNumber(event.target.value);
    });
})();
