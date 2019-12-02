var numHitsEl = document.getElementById("stats-num-hits");
window.setInterval(function() {
    let resultsCount = document.querySelectorAll("tbody tr.row").length;
    numHitsMsg = `${resultsCount.toLocaleString()}`;
    let numResultsEl = document.getElementById("num-results");
    if (numResultsEl) {
        let resultsTotal = parseInt(numResultsEl.dataset['resultsTotal']);
        let tookMs = parseInt(numResultsEl.dataset['tookMs']);
        numHitsMsg += ` of ${resultsTotal.toLocaleString()} results (took ${tookMs}ms)`;
    }
    numHitsEl.textContent = numHitsMsg;
}, 1000);

var histogramContainer = document.getElementById("histogram_container");
var histogramEl = document.getElementById("histogram");
var histogramRefresh = true;
function refreshHistogram() {
    if (!histogramRefresh) {
        return;
    }

    var newHistogramEl = document.createElement("object");
    newHistogramEl.type = histogramEl.type;
    newHistogramEl.data = histogramEl.data;
    newHistogramEl.style.display = "none";

    newHistogramEl.addEventListener("load", function() {
        histogramContainer.removeChild(histogramEl);
        newHistogramEl.id = "histogram";
        newHistogramEl.style.display = "";
        histogramEl = newHistogramEl;

        window.setTimeout(refreshHistogram, 5000);
    });
    histogramContainer.appendChild(newHistogramEl);
};
window.setTimeout(refreshHistogram, 5000);
window.addEventListener("DOMContentLoaded", function() {
    histogramRefresh = false;
});

var query = document.querySelector("#query");
var queryFilters = document.querySelectorAll(".field-filter");
for (let i = 0; i < queryFilters.length; i++) {
	let queryFilter = queryFilters[i];
	let removeFilterButton = makeElement("span", {
		"title": "Remove filter",
		"classList": "remove-filter",
		"onclick": function(ev) {
			queryFilter.parentElement.removeChild(queryFilter);
			query.submit();
		}
	}, "🗑");
    removeFilterButton.addEventListener("mouseenter", function(e) {
        queryFilter.style.backgroundColor="rgba(255, 0, 0, 0.7)";
        queryFilter.style.textDecoration="line-through";
    }, false);

    removeFilterButton.addEventListener("mouseout", function(e) {
        queryFilter.style.backgroundColor="transparent";
        queryFilter.style.textDecoration="initial";
    }, false);

	queryFilter.appendChild(removeFilterButton);
}

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
        let key = ev.target.parentElement.dataset['field'];
        let value = ev.target.parentElement.firstChild.textContent;
        addFilter(key, value, ev.target.classList.contains("filter-exclude"));
        return;
    }
});

function collectFieldStats(field) {
    var values = document.getElementsByClassName(field.dataset['class']);
    var total = 0;
    window.stats = {};
    for (var i = 0; i < values.length; i++) {
        var value = values[i].firstChild.textContent;
        stats[value] = (stats[value] || 0) + 1;
    };
    var top10 = Object.entries(stats).sort(([val1, cnt1], [val2, cnt2]) => cnt2 - cnt1).slice(0, 10);
    top10 = top10.map(([val, cnt]) => {
        var percent = Math.trunc((cnt / values.length) * 10000) / 100;
        val = val.replace(/[\n\t]+/g, " ");
        if (val.length > 79) {
            val = val.slice(0, 79) + "...";
        }
        return `${"=".repeat(percent * 0.7)}>
${val} = ${cnt} (${percent}%)`
    }).join("\n");
    alert(`Top 10 values of '${field.textContent}' in ${values.length} records:\n\n` + top10);
}

function expandSource(element) {
    var isExpanded = element.classList.contains("expanded");
    var sourceContainer = element.parentElement.nextElementSibling.firstElementChild;
    if (!isExpanded) {
        element.classList.add("expanded");
        var source = JSON.parse(element.parentElement.dataset['source']);
        var container = makeElement("div", {"class": "source-details"});
        var toggleTable = makeElement("a", {"href": "#"}, "Table");
        toggleTable.addEventListener("click", function(ev) {
            container.removeChild(container.lastElementChild);
            container.appendChild(renderSourceTable(source));
            ev.preventDefault();
        });
        var toggleJSON = makeElement("a", {"href": "#"}, "JSON");
        toggleJSON.addEventListener("click", function(ev) {
            container.removeChild(container.lastElementChild);
            container.appendChild(renderSourceJSON(source));
            ev.preventDefault();
        });
        container.appendChild(toggleTable);
        container.appendChild(new Text(" "));
        container.appendChild(toggleJSON);
        container.appendChild(renderSourceTable(source));
        sourceContainer.appendChild(container);
        sourceContainer.parentElement.classList.remove("source-hidden");
        element.textContent = "-";
    } else {
        sourceContainer.removeChild(sourceContainer.firstElementChild);
        sourceContainer.parentElement.classList.add("source-hidden");
        element.classList.remove("expanded");
        element.textContent = "+";
    }
}

function renderSourceJSON(source) {
    return makeElement("pre", {}, JSON.stringify(source, "", "  "));
}

function renderSourceTable(source) {
    let table = makeElement("table");
    let tbody = makeElement("tbody");
    Object.entries(flattenObject({}, "", source))
        .sort(([key1, _1], [key2, _2]) => {
            if (key1 < key2) {
                return -1;
            } else if (key1 > key2) {
                return 1;
            } else {
                return 0;
            }
        })
        .forEach(([key, value]) => {
            let row = makeElement("tr");

            let buttons = makeElement("td");
            buttons.appendChild(makeElement("span", {
                "title": "Filter for results matching value",
                "classList": "filter2 filter-include",
                "onclick": function() { addFilter(key, value, false); },
            }, "🔎"));
            buttons.appendChild(makeElement("span", {
                "title": "Exclude results matching value",
                "classList": "filter2 filter-exclude",
                "onclick": function() { addFilter(key, value, true); },
            }, "🗑"));
            buttons.appendChild(makeElement("span", {
                "title": "Add field",
                "classList": "filter2",
                "onclick": function() { addField(key); },
            }, "🗍"));
            buttons.appendChild(makeElement("span", {
                "title": "Require field to be present",
                "classList": "filter2",
                "onclick": function() { requireField(key); },
            }, "🞸"));

            row.appendChild(buttons);

            row.appendChild(makeElement("td", {}, key));
            row.appendChild(makeElement("td", {}, makeElement("pre", {}, (value === null ? "null" : value.toString()))));
            tbody.appendChild(row);
        })
    table.appendChild(tbody);
    return table;
}

function flattenObject(res, prefix, obj) {
    Object.entries(obj).forEach(([key, value]) => {
        if (!!value && value.constructor == Object) {
            flattenObject(res, (prefix ? prefix + "." : "") + key, value);
        } else {
            res[(prefix ? prefix + "." : "") + key] = value;
        }
    });
    return res;
}

function makeElement(tag, attrs, content) {
    let el = document.createElement(tag);
    for (key in attrs) {
        el[key] = attrs[key];
    }
    if (typeof content == "string") {
        el.textContent = content;
    } else if (content) {
        el.appendChild(content);
    }
    return el;
}

function addFilter(key, value, exclude) {
    if (exclude) {
        key = "-" + key;
    }
    var u = new URL(location.href);
    u.searchParams.append(key, value);
    location.href = u.href;
}

function requireField(fieldName) {
    var u = new URL(location.href);
    if (u.search == "") {
        u.search = "?" + fieldName;
    } else {
        u.search += "&" + fieldName;
    }
    location.href = u.href;
}

function addField(fieldName) {
    var u = new URL(location.href);
    if (u.searchParams.has("fields")) {
        u.searchParams.append("fields", fieldName);
    } else {
        u.searchParams.append("fields", "," + fieldName);
    }
    location.href = u.href;
}
