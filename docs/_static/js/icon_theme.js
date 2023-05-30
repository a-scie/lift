const Science = (() => {
    let iconsByImageId = {};
    return {
        theme: {
            registerIcons: (id, light, sepia, dark) => {
                iconsByImageId[id] = {
                    "light": light,
                    "sepia": sepia,
                    "dark": dark,
                }
            },
            updateMode: (mode) => {
                for (const [id, icons] of Object.entries(iconsByImageId)) {
                    const image = document.getElementById(id);
                    image.src = icons[mode] || icons.light
                }
            }
        }
    }
})();


Storage.prototype.__setItem = Storage.prototype.setItem;
Storage.prototype.setItem = (key, value) => {
    localStorage.__setItem(key, value);
    if (key === "sphinx-library-mode") {
        Science.theme.updateMode(value);
    }
};
