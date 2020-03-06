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

var histogramLinks = document.querySelector("#histogram_links");
var markdownButton = document.createElement("a");
markdownButton.textContent = "🗍";
markdownButton.title = "copy as markdown";
markdownButton.href = "#";
markdownButton.onclick = function(ev) {
	ev.preventDefault();

	let imageLink = new URL(location.href);
	imageLink.pathname = "/aggregation.svg";
	imageLink.searchParams.set("width", 900);
	imageLink.searchParams.set("height", 200);
	let asMarkdown = `[![visualization for ${location.href}](${imageLink})](${location.href})`;
	navigator.clipboard.writeText(asMarkdown).then(function() {
		markdownButton.style.color = "green";
		window.setTimeout(function() { markdownButton.style.color = ""; }, 1000);
	}, function() { alert("could not write to clipboard"); });
};
histogramLinks.insertBefore(document.createTextNode(" "), histogramLinks.firstElementChild);
histogramLinks.insertBefore(markdownButton, histogramLinks.firstChild);

var query = document.querySelector("#query");
var queryFilters = document.querySelectorAll(".field-filter");
for (let i = 0; i < queryFilters.length; i++) {
	let queryFilter = queryFilters[i];
	let removeFilterButton = queryFilter.querySelector(".remove-filter");
    removeFilterButton.addEventListener("mouseenter", function(e) {
        queryFilter.style.backgroundColor="lightgray";
        queryFilter.style.textDecoration="line-through";
    }, false);

    removeFilterButton.addEventListener("mouseout", function(e) {
        queryFilter.style.backgroundColor="transparent";
        queryFilter.style.textDecoration="initial";
    }, false);
}

let completions = {
    fieldNames: new Set(),
    fieldValues: new Map(),

    rowsScanned: 0,

    update: function(nameCompletionsEl) {
        let start = new Date();
        let rows = document.querySelectorAll(".results .row");
        for (let i = this.rowsScanned; i < rows.length; i++) {
            let source = JSON.parse(rows[i].dataset['source']);
            let flatSource = flattenObject({}, "", source);
            Object.entries(flatSource).forEach(([field, value]) => {
                if (!this.fieldValues.has(field)) {
                    this.fieldValues.set(field, new Set());
                    nameCompletionsEl.appendChild(makeElement("option", {
                        "value": field,
                    }, field));
                   if (typeof value == "string") {
                       nameCompletionsEl.appendChild(makeElement("option", {
                           "value": field + ".keyword",
                       }, field + ".keyword"));
                   }
                }

                this.fieldValues.get(field).add(flatSource[field]);
            });

            this.rowsScanned = i;
        }
        let end = new Date();
        console.log("completion took " + (end - start) + "ms");
    }
};

let newFieldEl = makeElement("span", {"classList": ["field-filter"]},
    [makeElement("input", {
        "type": "button",
        "value": "+",
        "title": "Add new filter",
        "onclick": function(ev) {
            // make params visible
            let fieldNameEl = newFieldEl.querySelector(".field-name");
            fieldNameEl.style = "display: inline-block";
            let fieldValueEl = newFieldEl.querySelector(".field-value");
            fieldValueEl.style = "display: inline-block";

            // focus on field-name
            fieldNameEl.focus();

            // calculate completion info
            let fieldNameCompletionEl = query.querySelector("#field-name-completion");
            completions.update(fieldNameCompletionEl);

            fieldNameEl.setAttribute("list", "field-name-completion");
            fieldValueEl.setAttribute("list", "field-value-completion");

            fieldNameEl.oninput = function(ev) {
                fieldValueEl.name = ev.target.value;
            }
        },
    }),
        document.createTextNode(" "),
        makeElement("input", {
            "type": "text",
            "placeholder": "field name",
            "autocomplete": "on",
            "classList": ["field-name"],
            "style": "display: none",
        }),
        makeElement("datalist", {"id": "field-name-completion"}),
        document.createTextNode(" "),
        makeElement("input", {
            "type": "text",
            "placeholder": "field content",
            "classList": ["field-value"],
            "style": "display: none",
            "onfocus": function(ev) {
                let completionsEl = ev.target.parentElement.querySelector("#field-value-completion");
                completionsEl.innerHTML = "";

                let values = completions.fieldValues.get(ev.target.name);
                if (values) {
                    values.forEach((value) => {
                        completionsEl.appendChild(makeElement("option", {
                            "value": value,
                        }, value));
                    });
                }
            },
        }),
        makeElement("datalist", {"id": "field-value-completion"}),
    ]
);
query.insertBefore(newFieldEl, query.querySelector(".meta"));

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
        let value = ev.target.parentElement.firstElementChild.textContent;
        addFilter(key, value, ev.target.classList.contains("filter-exclude"), redirect = true);
        return;
    }
});

document.querySelector(".results tbody").addEventListener('mouseover', function(ev) {
    if (ev.target.nodeName != "a" && !ev.target.classList.contains("filter")) {
        return;
    }

    let key = ev.target.parentElement.dataset['field'];
    let value = ev.target.parentElement.firstElementChild.textContent;
    ev.target.href = addFilter(key, value, ev.target.classList.contains("filter-exclude"));
});

function collectFieldStats(field) {
    var values = document.getElementsByClassName(field.dataset['class']);
    var total = 0;
    window.stats = {};
    for (var i = 0; i < values.length; i++) {
        var value = values[i].firstElementChild.textContent;
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
        var formattedFields = JSON.parse(element.parentElement.dataset['formattedFields']);
        var container = makeElement("div", {"class": "source-details"});
        var toggleTable = makeElement("a", {"href": "#"}, "Table");
        toggleTable.addEventListener("click", function(ev) {
            container.removeChild(container.lastElementChild);
            container.appendChild(renderSourceTable(source, formattedFields));
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
        container.appendChild(renderSourceTable(source, formattedFields));
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

function renderSourceTable(source, formattedFields) {
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
            buttons.appendChild(makeElement("a", {
                "title": "Filter for results matching value",
                "classList": "filter2 filter-include",
                "href": addFilter(key, value, false),
            }, "🔎"));
            buttons.appendChild(makeElement("a", {
                "title": "Exclude results matching value",
                "classList": "filter2 filter-exclude",
                "href": addFilter(key, value, true),
            }, "🗑"));
            buttons.appendChild(makeElement("a", {
                "title": "Add field",
                "classList": "filter2",
                "href": addField(key),
            }, "🗍"));
            buttons.appendChild(makeElement("a", {
                "title": "Require field to be present",
                "classList": "filter2",
                "href": requireField(key),
            }, "🞸"));

            row.appendChild(buttons);

            let valueEl = makeElement("pre", {}, (value === null ? "null" : value.toString()));

            if (key in formattedFields) {
                valueEl = makeElement("pre", {}, "");
                valueEl.innerHTML = formattedFields[key];
            }

            row.appendChild(makeElement("td", {}, key));
            row.appendChild(makeElement("td", {}, valueEl));
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
    } else if (content && content.forEach) {
        content.forEach((childEl) => el.appendChild(childEl));
    } else if (content) {
        el.appendChild(content);
    }
    return el;
}

function addFilter(key, value, exclude, redirect = false) {
    if (exclude) {
        key = "-" + key;
    }
    var u = new URL(location.href);
    u.searchParams.append(key, value);
    if (redirect) {
        location.href = u.href;
    }
    return u.href;
}

function requireField(fieldName) {
    var u = new URL(location.href);
    if (u.search == "") {
        u.search = "?" + fieldName;
    } else {
        u.search += "&" + fieldName;
    }
    return u.href
}

function addField(fieldName) {
    var u = new URL(location.href);
    if (u.searchParams.has("fields")) {
        u.searchParams.append("fields", fieldName);
    } else {
        u.searchParams.append("fields", "," + fieldName);
    }
    return u.href;
}
