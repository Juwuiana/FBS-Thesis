/**
 * Shared region -> city -> barangay cascade over the offline PSGC dataset
 * (data/psgc_data.json). Originally written once inline in nurse_intake.js
 * for patient intake; pulled out here so staff signup (public, pre-login)
 * and admin's Add Staff (server-rendered form) can use the same codes
 * instead of each hardcoding its own barangay list.
 *
 * Resolves by CODE, never by name -- see nurse_intake.js's own comment on
 * why (barangay names collide constantly across different cities/regions:
 * over 4,000 names are shared by more than one barangay nationwide).
 *
 * Usage:
 *   initPsgcCascade({
 *     psgcUrl: window.__psgcUrl,
 *     regionSelect: document.getElementById('region'),
 *     citySelect: document.getElementById('city'),
 *     barangaySelect: document.getElementById('barangay_select'),
 *     barangayManual: document.getElementById('barangay_manual'), // optional
 *     hidden: {
 *       regionCode, regionName, cityCode, cityName,
 *       barangayCode, barangayName,               // elements, not strings
 *     },
 *     preselect: { regionCode, cityCode, barangayCode, barangayName }, // optional
 *   });
 */
function initPsgcCascade(config) {
    const { psgcUrl, regionSelect, citySelect, barangaySelect, barangayManual, hidden, preselect } = config;
    let psgcData = null;

    function fillSelect(select, items, placeholder) {
        select.innerHTML = '';
        const opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = placeholder;
        select.appendChild(opt0);
        items.forEach(({ code, name }) => {
            const opt = document.createElement('option');
            opt.value = code;
            opt.textContent = name;
            select.appendChild(opt);
        });
    }

    function setHidden(field, value) {
        if (hidden && hidden[field]) hidden[field].value = value || '';
    }

    function syncHiddenFromSelection() {
        const regionOpt = regionSelect.options[regionSelect.selectedIndex];
        const cityOpt = citySelect.options[citySelect.selectedIndex];
        setHidden('regionCode', regionSelect.value || '');
        setHidden('regionName', regionSelect.value ? regionOpt.textContent : '');
        setHidden('cityCode', citySelect.value || '');
        setHidden('cityName', citySelect.value ? cityOpt.textContent : '');

        if (barangayManual && barangayManual.style.display !== 'none' && barangayManual.value.trim()) {
            setHidden('barangayCode', '');
            setHidden('barangayName', barangayManual.value.trim());
        } else if (barangaySelect.value) {
            const bOpt = barangaySelect.options[barangaySelect.selectedIndex];
            setHidden('barangayCode', barangaySelect.value);
            setHidden('barangayName', bOpt.textContent);
        } else {
            setHidden('barangayCode', '');
            setHidden('barangayName', '');
        }
    }

    function populateCities(regionCode) {
        const cities = psgcData.cities
            .filter((c) => c.regionCode === regionCode)
            .sort((a, b) => a.name.localeCompare(b.name));
        fillSelect(citySelect, cities, cities.length ? 'Select City / Municipality' : 'No cities found');
        citySelect.disabled = cities.length === 0;
        fillSelect(barangaySelect, [], 'Select City first');
        barangaySelect.disabled = true;
        if (barangayManual) { barangayManual.style.display = 'none'; }
    }

    function populateBarangays(cityCode) {
        const brgys = psgcData.barangays
            .filter((b) => b.cityCode === cityCode)
            .sort((a, b) => a.name.localeCompare(b.name));
        if (brgys.length) {
            fillSelect(barangaySelect, brgys, 'Select Barangay');
            barangaySelect.disabled = false;
            if (barangayManual) { barangayManual.style.display = 'none'; barangayManual.value = ''; }
        } else {
            // Some cities (e.g. City of Manila) have no direct barangay list --
            // their districts carry the barangays instead. Fall back to
            // manual entry rather than blocking the form.
            fillSelect(barangaySelect, [], 'Not available — type below');
            barangaySelect.disabled = true;
            if (barangayManual) barangayManual.style.display = 'block';
        }
    }

    regionSelect.addEventListener('change', () => {
        if (!psgcData) return;
        if (!regionSelect.value) {
            fillSelect(citySelect, [], 'Select Region first');
            citySelect.disabled = true;
            fillSelect(barangaySelect, [], 'Select City first');
            barangaySelect.disabled = true;
            if (barangayManual) barangayManual.style.display = 'none';
        } else {
            populateCities(regionSelect.value);
        }
        syncHiddenFromSelection();
    });

    citySelect.addEventListener('change', () => {
        if (!psgcData || !regionSelect.value) return;
        if (!citySelect.value) {
            fillSelect(barangaySelect, [], 'Select City first');
            barangaySelect.disabled = true;
            if (barangayManual) barangayManual.style.display = 'none';
        } else {
            populateBarangays(citySelect.value);
        }
        syncHiddenFromSelection();
    });

    barangaySelect.addEventListener('change', syncHiddenFromSelection);
    if (barangayManual) barangayManual.addEventListener('input', syncHiddenFromSelection);

    if (!psgcUrl) return;

    fetch(psgcUrl)
        .then((res) => res.json())
        .then((data) => {
            psgcData = data;
            fillSelect(regionSelect, data.regions, 'Select Region');

            // Re-show a previous selection after the form comes back with a
            // validation error, so the person doesn't have to re-pick region
            // -> city -> barangay from scratch.
            if (preselect && preselect.regionCode) {
                regionSelect.value = preselect.regionCode;
                populateCities(preselect.regionCode);
                if (preselect.cityCode) {
                    citySelect.value = preselect.cityCode;
                    populateBarangays(preselect.cityCode);
                    if (preselect.barangayCode) {
                        barangaySelect.value = preselect.barangayCode;
                    } else if (preselect.barangayName && barangayManual) {
                        barangayManual.style.display = 'block';
                        barangayManual.value = preselect.barangayName;
                    }
                }
            }
            syncHiddenFromSelection();
        })
        .catch((err) => {
            console.error('Could not load region/city/barangay data:', err);
            regionSelect.innerHTML = '<option value="">Unavailable</option>';
            citySelect.innerHTML = '<option value="">Unavailable</option>';
            barangaySelect.disabled = true;
            if (barangayManual) barangayManual.style.display = 'block';
        });
}
