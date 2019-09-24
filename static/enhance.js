var numHitsEl = document.getElementById("stats-num-hits");
window.setInterval(function() {
    numHitsEl.textContent = document.querySelectorAll("tbody tr.row").length;
}, 1000);

document.body.addEventListener('click', function(ev) {
    if (ev.target.classList.contains("toggle-expand")) {
        expandSource(ev.target);
        return;
    }

    if (ev.target.classList.contains("field")) {
        collectFieldStats(ev.target);
        return;
    }

    if (ev.target.classList.contains("filter")) {
        addFilter(ev.target);
        return;
    }
});

function collectFieldStats(field) {
    var values = document.getElementsByClassName(field.dataset['class']);
    var total = 0;
    window.stats = {};
    for (var i = 0; i < values.length; i++) {
        var value = values[i].textContent;
        stats[value] = (stats[value] || 0) + 1;
    };
    var top10 = Object.entries(stats).sort(([val1, cnt1], [val2, cnt2]) => cnt2 - cnt1).slice(0, 10);
    top10 = top10.map(([val, cnt]) => {
        var percent = Math.trunc((cnt / values.length) * 10000) / 100;
        val = val.replace(/[\n\t]+/g, " ");
        if (val.length > 79) {
            val = val.slice(0, 79) + "...";
        }
        return `${val} = ${cnt} (${percent}%)`
    }).join("\n");
    alert(`Top 10 values of '${field.textContent}' in ${values.length} records:\n\n` + top10);
}

function expandSource(element) {
    var isExpanded = element.classList.contains("expanded");
    var sourceContainer = element.parentElement.nextElementSibling.firstElementChild;
    if (!isExpanded) {
        element.classList.add("expanded");
        var source = JSON.stringify(JSON.parse(element.parentElement.dataset['source']), "", "  ");
        var formattedSourceEl = document.createElement("pre");
        formattedSourceEl.textContent = source;
        sourceContainer.appendChild(formattedSourceEl);
        sourceContainer.parentElement.classList.remove("source-hidden");
        element.textContent = "-";
    } else {
        sourceContainer.removeChild(sourceContainer.firstElementChild);
        sourceContainer.parentElement.classList.add("source-hidden");
        element.classList.remove("expanded");
        element.textContent = "+";
    }
}

function addFilter(element) {
    var key = element.parentElement.dataset['field'];
    if (element.classList.contains("filter-exclude")) {
        key = "-" + key;
    }
    var u = new URL(location.href);
    u.searchParams.append(key, element.parentElement.firstChild.textContent);
    location.href = u.href;
}
