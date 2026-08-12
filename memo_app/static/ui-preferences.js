(() => {
    const themeKey = 'memo-garden-theme';
    const nav = document.querySelector('.site-nav');
    if (!nav) return;
    const themeButton = document.createElement('button');
    themeButton.className = 'preference-button';
    themeButton.id = 'theme-toggle';
    themeButton.type = 'button';
    themeButton.setAttribute('aria-label', '表示テーマを切り替える');
    nav.append(themeButton);

    let theme = localStorage.getItem(themeKey) || 'light';
    const applyTheme = () => {
        const dark = theme === 'dark';
        document.body.classList.toggle('dark-theme', dark);
        themeButton.textContent = dark ? '☀' : '☾';
        themeButton.title = dark ? 'ライトモード' : 'ダークモード';
    };
    applyTheme();
    themeButton.addEventListener('click', () => {
        theme = theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem(themeKey, theme);
        applyTheme();
    });
})();
