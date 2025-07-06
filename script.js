(() => {
  let priceMap = {};

  // ========================
  // 🔌 FETCH PRICES
  // ========================
  async function fetchSalesPrices() {
    try {
      const res = await fetch("/api/get_all_prices");
      priceMap = res.ok ? await res.json() : {};
    } catch (err) {
      console.error("Error fetching prices:", err);
      priceMap = {};
    }
  }

  // ========================
  // 💰 PRICE CALCULATION
  // ========================
  function getPrice(battery, type) {
    if (!battery) return 0;
    const data = priceMap[battery.trim()] || {};
    switch (type) {
      case 'Dealer': return data.DP || 0;
      case 'Customer': return data.MRP || 0;
      case 'Garage': return data.Garage || 0;
      case 'Free Replacement':
        return (data.DP && data.OldPrice) ? Math.max(0, data.DP - data.OldPrice) : 0;
      case 'Old': return data.OldPrice || 0;
      default: return 0;
    }
  }

  // ========================
  // 🔄 POPULATE BATTERY OPTIONS FOR DATALIST
  // ========================
  function populateBatteryOptions(type) {
    // For newBattery datalist
    const datalist = document.getElementById('batteryList');
    if (!datalist) return;
    datalist.innerHTML = '';
    Object.entries(priceMap).forEach(([bat, data]) => {
      const ok = (type === 'Dealer' && data.DP) ||
                 (type === 'Customer' && data.MRP) ||
                 (type === 'Garage' && data.Garage) ||
                 (type === 'Free Replacement' && data.DP && data.OldPrice);
      if (ok) {
        const option = document.createElement('option');
        option.value = bat.trim();
        datalist.appendChild(option);
      }
    });

    // For oldBattery datalist (used in old battery rows)
    const oldBatteryDatalist = document.getElementById('oldBatteryList');
    if (!oldBatteryDatalist) return;
    oldBatteryDatalist.innerHTML = '';
    Object.keys(priceMap).forEach(bat => {
      const option = document.createElement('option');
      option.value = bat.trim();
      oldBatteryDatalist.appendChild(option);
    });
  }

  // ========================
  // 📦 OLD BATTERY HANDLING
  // ========================

  // Add old battery datalist to body once
  function addOldBatteryDatalist() {
    if (document.getElementById('oldBatteryList')) return;
    const datalist = document.createElement('datalist');
    datalist.id = 'oldBatteryList';
    document.body.appendChild(datalist);
  }

  function addOldRow() {
    const tbody = document.querySelector('#oldBatteryTable tbody');
    if (!tbody) return;
    addOldBatteryDatalist();

    const optsDatalistId = 'oldBatteryList';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input list="${optsDatalistId}" class="oldBatteryInput" required placeholder="Select or type battery" autocomplete="off" /></td>
      <td><input type="number" class="oldBatteryQty" min="1" value="1" required /></td>
      <td><button type="button" class="remove">❌</button></td>
    `;

    const batteryInput = tr.querySelector('.oldBatteryInput');
    const qtyInput = tr.querySelector('.oldBatteryQty');
    const removeBtn = tr.querySelector('.remove');

    batteryInput.addEventListener('input', recalcOldTotal);
    qtyInput.addEventListener('input', recalcOldTotal);
    removeBtn.addEventListener('click', () => {
      tr.remove();
      recalcOldTotal();
    });

    tbody.appendChild(tr);
  }

  function recalcOldTotal() {
    let sum = 0;
    document.querySelectorAll('#oldBatteryTable tbody tr').forEach(tr => {
      const bat = tr.querySelector('.oldBatteryInput')?.value.trim() || '';
      const qty = parseInt(tr.querySelector('.oldBatteryQty')?.value) || 0;
      sum += getPrice(bat, 'Old') * qty;
    });
    document.getElementById('oldBatteryTotal').value = sum.toFixed(2);
    recalcTotal();
  }

  // ========================
  // 💵 TOTAL & FINAL CALCULATIONS
  // ========================
  function recalcTotal() {
    const price = parseFloat(document.getElementById('batteryPrice')?.value) || 0;
    const qty = parseInt(document.getElementById('quantity')?.value) || 0;
    const oldTot = parseFloat(document.getElementById('oldBatteryTotal')?.value) || 0;
    const salesType = document.getElementById('salesType')?.value;

    let total;

    if (salesType === 'Free Replacement') {
      total = price * qty;
    } else {
      total = price * qty - oldTot;
    }

    document.getElementById('totalRupees').value = total.toFixed(2);
    recalcFinal();
  }

  function recalcFinal() {
    const tot = parseFloat(document.getElementById('totalRupees')?.value) || 0;
    const disc = parseFloat(document.getElementById('discount')?.value) || 0;
    document.getElementById('finalAmount').value = Math.max(0, tot - disc).toFixed(2);
  }

  // ========================
  // ⚙️ SETUP EVENTS FOR SALES PAGE
  // ========================
  function setupSalesEvents() {
    const typeSel = document.getElementById('salesType');
    if (!typeSel) return;

    const batInput = document.getElementById('newBattery');
    const priceIn = document.getElementById('batteryPrice');
    const qtyIn = document.getElementById('quantity');
    const discIn = document.getElementById('discount');
    const oldField = document.getElementById('oldBatteryFieldset');

    typeSel.addEventListener('change', () => {
      populateBatteryOptions(typeSel.value);
      priceIn.value = '';
      qtyIn.value = 1;
      discIn.value = 0;
      document.getElementById('totalRupees').value = '';
      document.getElementById('finalAmount').value = '';
      document.getElementById('oldBatteryTotal').value = '';
      const tbody = document.querySelector('#oldBatteryTable tbody');
      if (tbody) tbody.innerHTML = '';

      if (typeSel.value === 'Free Replacement') {
        oldField.style.display = 'none';
        document.getElementById('oldBatteryTotal').value = '0.00';
      } else {
        oldField.style.display = 'block';
        addOldRow();
      }
    });

    batInput.addEventListener('input', () => {
      const batVal = batInput.value.trim();
      if (batVal in priceMap) {
        priceIn.value = getPrice(batVal, typeSel.value).toFixed(2);
      } else {
        priceIn.value = '';
      }
      // Update first old battery row battery input if needed:
      const firstRow = document.querySelector('#oldBatteryTable tbody tr');
      if (firstRow) {
        const batteryInput = firstRow.querySelector('.oldBatteryInput');
        const qtyInput = firstRow.querySelector('.oldBatteryQty');
        if (batteryInput && qtyInput) {
          batteryInput.value = batVal in priceMap ? batVal : '';
          qtyInput.value = 1;
        }
      }
      recalcOldTotal();
    });

    qtyIn.addEventListener('input', recalcTotal);
    discIn.addEventListener('input', recalcFinal);
    document.getElementById('addOldBatteryBtn')?.addEventListener('click', addOldRow);

    document.getElementById('salesForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();

      const oldBatteries = Array.from(document.querySelectorAll('#oldBatteryTable tbody tr'))
        .map(row => {
          const battery = row.querySelector('.oldBatteryInput')?.value.trim() || '';
          const qty = parseInt(row.querySelector('.oldBatteryQty')?.value) || 0;
          return (battery && qty > 0) ? { battery, qty } : null;
        })
        .filter(Boolean);

      const payload = {
        saleDate: document.getElementById('saleDate')?.value,
        salesType: document.getElementById('salesType')?.value,
        newBattery: document.getElementById('newBattery')?.value,
        quantity: document.getElementById('quantity')?.value,
        batteryPrice: document.getElementById('batteryPrice')?.value,
        oldBatteries,
        oldBatteryTotal: document.getElementById('oldBatteryTotal')?.value,
        totalRupees: document.getElementById('totalRupees')?.value,
        discount: document.getElementById('discount')?.value,
        finalAmount: document.getElementById('finalAmount')?.value
      };

      try {
        const res = await fetch('/api/save_sales', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        alert(result.message || "Sale saved!");
        location.reload();
      } catch (err) {
        alert("Error saving sale.");
        console.error(err);
      }
    });
  }

  // ========================
  // 💼 EXPENSE PAGE LOGIC (unchanged, but kept for completeness)
  // ========================
  function setupExpenseEvents() {
    const categorySelect = document.getElementById("category");
    const customWrapper = document.getElementById("customCategoryWrapper");
    const customInput = document.getElementById("customCategory");
    const expenseForm = document.querySelector("form[action='/expense']");

    if (!categorySelect || !customWrapper || !expenseForm) return;

    categorySelect.addEventListener("change", () => {
      if (categorySelect.value === "Other") {
        customWrapper.style.display = "block";
      } else {
        customWrapper.style.display = "none";
        customInput.value = "";
      }
    });

    expenseForm.addEventListener("submit", (e) => {
      if (categorySelect.value === "Other") {
        const customVal = customInput.value.trim();
        if (!customVal) {
          alert("Please specify a custom category.");
          e.preventDefault();
          return;
        }
        const hiddenInput = document.createElement("input");
        hiddenInput.type = "hidden";
        hiddenInput.name = "category";
        hiddenInput.value = customVal;
        expenseForm.appendChild(hiddenInput);
        categorySelect.disabled = true;
      }
    });
  }

  // ========================
  // 🚀 INIT
  // ========================
  document.addEventListener('DOMContentLoaded', async () => {
    if (document.getElementById('salesForm')) {
      await fetchSalesPrices();
      populateBatteryOptions('Dealer');
      setupSalesEvents();
      addOldRow();
    }

    setupExpenseEvents();
  });
})();
