window.addEventListener("DOMContentLoaded", () => {
    const buttons = document.getElementById("sidebar").children;
    for (const [i, elem] of [...buttons].entries()) {
        elem.addEventListener("click", () => {
            for (const other of buttons) {
                other.classList.remove("active");
            }
            elem.classList.add("active");
            for (const [j, content] of [...document.getElementsByClassName("content")].entries()) {
                if (i === j) content.classList.add("visible"); 
                else content.classList.remove("visible");
            }
        });
    }

    for (const elem of document.getElementsByClassName("spoiler")) {
        elem.addEventListener("click", () => {
            elem.classList.add("spoiler-shown");
        });
    }

    for (const elem of document.getElementsByTagName("time")) {
        const format = {
            "t": {hour: "2-digit", minute: "2-digit"},
            "T": {hour: "2-digit", minute: "2-digit", second: "2-digit"},
            "d": {year: "2-digit", month: "2-digit", day: "2-digit"},
            "D": {year: "numeric", month: "long", day: "numeric"},
            "f": {year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"},
            "F": {weekday: "long", year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"},
            "s": {year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"},
            "S": {year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"},
            "R": {year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit"},
        }[elem.dataset.format];
        elem.innerText = (new Date(elem.innerText)).toLocaleString(undefined, format);
    }

    for (const elem of document.getElementsByClassName("user")) {
        elem.addEventListener("click", () => {
            const id = elem.dataset.id;
            elem.dataset.id = elem.innerText;
            elem.innerText = id;
        });
    }

    for (const elem of document.getElementsByClassName("goto")) {
        elem.addEventListener("click", () => {
            buttons[+elem.dataset.goto].click();
        });
    }
});
