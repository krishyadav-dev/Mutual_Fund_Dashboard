/*
 * index.js — Core Controller and Visualisation Engine
 * Mutual Fund Dashboard
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- STATE ---
  let fundMetrics = [];
  let rollingReturns = [];
  let categoryAUM = [];
  let selectedCompareCodes = [];
  let activeCategory = "ALL";
  let activeAMC = "ALL";
  let activeSearch = "";
  let activeMaxExpense = "ALL";
  let activeMinAUM = "ALL";
  let activeMinStars = "ALL";
  let fundAumHistory = [];
  let lastKnownModifiedTime = null;
  
  // Sort Column State
  let activeSortColumn = "composite_score";
  let activeSortDirection = "desc";

  // Charts State
  let riskReturnChartInstance = null;
  let aumChartInstance = null;
  let rollingReturnsChartInstance = null;
  let deepdiveAumChartInstance = null;
  let costCalculatorChartInstance = null;
  let selectedRollingCodes = []; // Funds selected for line chart
  let activeDeepdiveCode = null; // Currently selected fund scheme code for Deep Dive

  // Category Theme Colors for charts (Muted, minimalist palettes)
  const categoryColors = {
    "Equity Scheme": { color: "#22d3ee", bg: "rgba(34, 211, 238, 0.15)" },      // Cyan
    "Hybrid Scheme": { color: "#fbbf24", bg: "rgba(251, 191, 36, 0.15)" },      // Amber
    "Debt Scheme": { color: "#60a5fa", bg: "rgba(96, 165, 250, 0.15)" },       // Blue
    "Other Scheme": { color: "#818cf8", bg: "rgba(129, 140, 248, 0.15)" }       // Indigo
  };
  const defaultColor = { color: "#94a3b8", bg: "rgba(148, 163, 184, 0.15)" };

  // --- RFC-4180 COMPLIANT CSV PARSER ---
  function parseCSV(text) {
    const lines = [];
    let row = [""];
    let inQuotes = false;
    
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      const nextChar = text[i + 1];
      
      if (char === '"') {
        if (inQuotes && nextChar === '"') {
          row[row.length - 1] += '"';
          i++; // Skip double quote escape
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === ',') {
        if (inQuotes) {
          row[row.length - 1] += ',';
        } else {
          row.push("");
        }
      } else if (char === '\r' || char === '\n') {
        if (inQuotes) {
          row[row.length - 1] += char;
        } else {
          if (char === '\r' && nextChar === '\n') {
            i++;
          }
          lines.push(row);
          row = [""];
        }
      } else {
        row[row.length - 1] += char;
      }
    }
    
    if (row.length > 1 || row[0] !== "") {
      lines.push(row);
    }
    
    if (lines.length === 0) return [];
    
    const headers = lines[0].map(h => h.trim());
    const data = [];
    
    for (let i = 1; i < lines.length; i++) {
      const row = lines[i];
      if (row.length !== headers.length) continue;
      const obj = {};
      for (let j = 0; j < headers.length; j++) {
        obj[headers[j]] = row[j].trim();
      }
      data.push(obj);
    }
    return data;
  }

  // --- INITIAL DATA FETCH ---
  async function loadData() {
    try {
      showTableShimmerLoaders();

      // Fetch file 1: fund_metrics.csv
      const metricsResponse = await fetch("data/output/fund_metrics.csv");
      if (!metricsResponse.ok) throw new Error("Failed to fetch fund metrics CSV");

      // Save Last-Modified timestamp to track updates
      const modifiedTime = metricsResponse.headers.get("Last-Modified");
      if (modifiedTime) {
        lastKnownModifiedTime = modifiedTime;
      }

      const metricsText = await metricsResponse.text();
      fundMetrics = parseCSV(metricsText);

      // Parse numerical metrics
      fundMetrics.forEach(d => {
        d.scheme_code = parseInt(d.scheme_code);
        d.cagr_1y = parseFloat(d.cagr_1y) || null;
        d.cagr_3y = parseFloat(d.cagr_3y) || null;
        d.cagr_5y = parseFloat(d.cagr_5y) || null;
        d.volatility_pct = parseFloat(d.volatility_pct) || null;
        d.sharpe_ratio = parseFloat(d.sharpe_ratio) || null;
        d.sortino_ratio = parseFloat(d.sortino_ratio) || null;
        d.calmar_ratio = parseFloat(d.calmar_ratio) || null;
        d.max_drawdown_pct = parseFloat(d.max_drawdown_pct) || null;
        d.beta = parseFloat(d.beta) || null;
        d.alpha_pct = parseFloat(d.alpha_pct) || null;
        d.tracking_error_pct = parseFloat(d.tracking_error_pct) || null;
        d.expense_ratio_pct = parseFloat(d.expense_ratio_pct) || null;
        d.aum_cr = parseFloat(d.aum_cr) || null;
        d.morningstar_stars = parseInt(d.morningstar_stars) || null;
        d.return_per_cost = parseFloat(d.return_per_cost) || null;
        d.return_per_cost_rank = parseInt(d.return_per_cost_rank) || null;
        d.true_net_return = parseFloat(d.true_net_return) || null;
        d.composite_score = parseFloat(d.composite_score) || 0;
        d.universe_rank = parseInt(d.universe_rank) || 0;
        d.category_rank = parseInt(d.category_rank) || 0;
        d.latest_nav = parseFloat(d.latest_nav) || 0;
        d.nav_52w_high = parseFloat(d.nav_52w_high) || 0;
        d.nav_52w_low = parseFloat(d.nav_52w_low) || 0;
        d.nav_52w_change_pct = parseFloat(d.nav_52w_change_pct) || 0;
        d.fund_age_years = parseFloat(d.fund_age_years) || 0;
      });

      // Default the deep dive active selection if not set
      if (!activeDeepdiveCode && fundMetrics.length > 0) {
        activeDeepdiveCode = fundMetrics[0].scheme_code;
      }

      // Fetch file 2: rolling_returns.csv
      const rollingResponse = await fetch("data/output/rolling_returns.csv");
      if (rollingResponse.ok) {
        const rollingText = await rollingResponse.text();
        rollingReturns = parseCSV(rollingText);
        rollingReturns.forEach(d => {
          d.scheme_code = parseInt(d.scheme_code);
          d.rolling_1y_return_pct = parseFloat(d.rolling_1y_return_pct) || 0;
        });
      }

      // Fetch file 2b: fund_aum_history.csv
      const aumHistoryResponse = await fetch("data/output/fund_aum_history.csv");
      if (aumHistoryResponse.ok) {
        const aumHistoryText = await aumHistoryResponse.text();
        fundAumHistory = parseCSV(aumHistoryText);
        fundAumHistory.forEach(d => {
          d.scheme_code = parseInt(d.scheme_code);
          d.aum_cr = parseFloat(d.aum_cr) || 0;
        });
      }

      // Fetch file 3: aum_amfi_monthly_clean.csv
      const aumResponse = await fetch("data/cleaned/aum_amfi_monthly_clean.csv");
      if (aumResponse.ok) {
        const aumText = await aumResponse.text();
        categoryAUM = parseCSV(aumText);
        categoryAUM.forEach(d => {
          d.aum_cr = parseFloat(d.aum_cr) || 0;
          d.num_schemes = parseFloat(d.num_schemes) || 0;
          d.num_folios = parseFloat(d.num_folios) || 0;
        });
      }

      // Set default rolling line chart selections to top 3 composite funds if not already set
      if (!selectedRollingCodes || selectedRollingCodes.length === 0) {
        const topFunds = [...fundMetrics]
          .sort((a, b) => b.composite_score - a.composite_score)
          .slice(0, 3)
          .map(f => f.scheme_code);
        selectedRollingCodes = topFunds;
      }

      // Populate elements
      populateAMCs();
      populateDeepdiveSelector();
      updateDashboardStats();
      updateSortHeaderClasses();
      renderScreener();
      renderRollingSelectors();

      // Maintain selection consistency on data updates
      selectedCompareCodes = selectedCompareCodes.filter(code => fundMetrics.some(f => f.scheme_code === code));
      updateCompareBar();
      
      // Update visual tab if it was already rendered
      if (document.getElementById("visuals-page").classList.contains("active")) {
        renderCharts();
      }

      // Update comparison tab if it was already active
      if (document.getElementById("compare-page").classList.contains("active")) {
        renderComparison();
      }

    } catch (error) {
      console.error("Data loading error:", error);
      alert("Error loading dashboard data. Make sure data/output contains the pipeline CSVs.");
    }
  }

  // --- HELPERS ---
  function showTableShimmerLoaders() {
    const tbody = document.getElementById("screener-tbody");
    tbody.innerHTML = Array(6).fill(0).map(() => `
      <tr>
        <td style="text-align: center;"><div class="loading-shimmer-row" style="width: 16px; height: 16px; border-radius: 4px; margin: 0 auto;"></div></td>
        <td>
          <div class="loading-shimmer-row" style="width: 180px; height: 14px; border-radius: 4px; margin-bottom: 6px;"></div>
          <div class="loading-shimmer-row" style="width: 100px; height: 10px; border-radius: 4px;"></div>
        </td>
        <td><div class="loading-shimmer-row" style="width: 70px; height: 16px; border-radius: 4px;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 50px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 50px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 40px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 40px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 50px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 70px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 40px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
        <td><div class="loading-shimmer-row" style="width: 30px; height: 14px; border-radius: 4px; margin-left: auto;"></div></td>
      </tr>
    `).join('');
  }

  function getCategoryTheme(category) {
    return categoryColors[category] || defaultColor;
  }

  // --- STATS BOARD ---
  function updateDashboardStats() {
    if (fundMetrics.length === 0) return;

    // 1. Top Compounder (CAGR 3Y)
    const topCAGRFund = [...fundMetrics]
      .filter(d => d.cagr_3y !== null)
      .reduce((prev, current) => (prev.cagr_3y > current.cagr_3y) ? prev : current);
    
    document.getElementById("stat-top-cagr").innerText = `${topCAGRFund.cagr_3y.toFixed(1)}%`;
    document.getElementById("stat-top-cagr-name").innerHTML = `<span class="text-profit" style="margin-right: 4px; font-size: 0.8rem;">▲</span> ${truncateString(topCAGRFund.fund_name, 22)}`;
    document.getElementById("stat-top-cagr-name").title = topCAGRFund.fund_name;

    // 2. Highest Sharpe
    const topSharpeFund = [...fundMetrics]
      .filter(d => d.sharpe_ratio !== null)
      .reduce((prev, current) => (prev.sharpe_ratio > current.sharpe_ratio) ? prev : current);

    document.getElementById("stat-top-sharpe").innerText = topSharpeFund.sharpe_ratio.toFixed(2);
    document.getElementById("stat-top-sharpe-name").innerHTML = `<span style="color: #60a5fa; margin-right: 4px; font-size: 0.8rem;">✦</span> ${truncateString(topSharpeFund.fund_name, 22)}`;
    document.getElementById("stat-top-sharpe-name").title = topSharpeFund.fund_name;

    // 3. Lowest Volatility
    const minVolFund = [...fundMetrics]
      .filter(d => d.volatility_pct !== null && d.volatility_pct > 0)
      .reduce((prev, current) => (prev.volatility_pct < current.volatility_pct) ? prev : current);

    document.getElementById("stat-min-vol").innerText = `${minVolFund.volatility_pct.toFixed(1)}%`;
    document.getElementById("stat-min-vol-name").innerHTML = `<span class="text-profit" style="margin-right: 4px; font-size: 0.8rem;">▼</span> ${truncateString(minVolFund.fund_name, 22)}`;
    document.getElementById("stat-min-vol-name").title = minVolFund.fund_name;

    // 4. Size
    document.getElementById("stat-universe-size").innerText = fundMetrics.length;
  }

  function truncateString(str, num) {
    if (str.length <= num) return str;
    return str.slice(0, num) + '...';
  }

  // --- AMC SELECT POPULATION ---
  function populateAMCs() {
    const amcSelect = document.getElementById("amc-select");
    const uniqueAMCs = [...new Set(fundMetrics.map(f => f.fund_house))].sort();
    
    amcSelect.innerHTML = `<option value="ALL">All Asset Managers</option>`;
    
    uniqueAMCs.forEach(amc => {
      const option = document.createElement("option");
      option.value = amc;
      option.innerText = amc.replace("Mutual Fund", "").trim();
      amcSelect.appendChild(option);
    });
  }

  // --- SCREENER ENGINE ---
  function renderScreener() {
    const tbody = document.getElementById("screener-tbody");
    
    // Apply filters
    let filtered = fundMetrics.filter(fund => {
      // 1. Broad Category Filter
      const catMatch = (activeCategory === "ALL") || (fund.broad_category === activeCategory);
      
      // 2. AMC/Fund House Filter
      const amcMatch = (activeAMC === "ALL") || (fund.fund_house === activeAMC);
      
      // 3. Search text
      const searchMatch = (activeSearch === "") || 
        fund.fund_name.toLowerCase().includes(activeSearch.toLowerCase()) ||
        fund.fund_house.toLowerCase().includes(activeSearch.toLowerCase());
        
      // 4. Max Expense Ratio Filter
      const expMatch = (activeMaxExpense === "ALL") || (fund.expense_ratio_pct !== null && fund.expense_ratio_pct <= parseFloat(activeMaxExpense));
      
      // 5. Min AUM Filter
      const aumMatch = (activeMinAUM === "ALL") || (fund.aum_cr !== null && fund.aum_cr >= parseFloat(activeMinAUM));
      
      // 6. Min Stars Filter
      const starsMatch = (activeMinStars === "ALL") || (fund.morningstar_stars !== null && fund.morningstar_stars >= parseInt(activeMinStars));
      
      return catMatch && amcMatch && searchMatch && expMatch && aumMatch && starsMatch;
    });

    // Apply Sorting
    filtered.sort((a, b) => {
      let valA = a[activeSortColumn];
      let valB = b[activeSortColumn];

      // Handle nulls (always place at bottom)
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;

      // Handle text vs numeric sorting
      if (typeof valA === "string") {
        return activeSortDirection === "asc" 
          ? valA.localeCompare(valB) 
          : valB.localeCompare(valA);
      } else {
        return activeSortDirection === "asc"
          ? valA - valB
          : valB - valA;
      }
    });

    // Render Rows
    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
            <i class="fa-solid fa-folder-open" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
            No mutual funds match your filter criteria.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered.map(fund => {
      const isChecked = selectedCompareCodes.includes(fund.scheme_code);
      
      // Map badge subclass
      let badgeClass = "equity";
      if (fund.broad_category === "Hybrid Scheme") badgeClass = "hybrid";
      if (fund.broad_category === "Debt Scheme") badgeClass = "debt";
      if (fund.broad_category === "Other Scheme") badgeClass = "index";

      const cagr3Y = fund.cagr_3y ? `${fund.cagr_3y.toFixed(1)}%` : "N/A";
      const cagr1Y = fund.cagr_1y ? `${fund.cagr_1y.toFixed(1)}%` : "N/A";
      const sharpe = fund.sharpe_ratio ? fund.sharpe_ratio.toFixed(2) : "N/A";
      const volatility = fund.volatility_pct ? `${fund.volatility_pct.toFixed(1)}%` : "N/A";
      const mdd = fund.max_drawdown_pct ? `${fund.max_drawdown_pct.toFixed(1)}%` : "N/A";
      
      // Star rating stars column HTML
      let starsHtml = "";
      if (fund.morningstar_stars) {
        for (let s = 1; s <= 5; s++) {
          if (s <= fund.morningstar_stars) {
            starsHtml += `<i class="fa-solid fa-star star-gold"></i>`;
          } else {
            starsHtml += `<i class="fa-solid fa-star star-grey"></i>`;
          }
        }
      } else {
        starsHtml = `<span style="color: var(--text-muted);">—</span>`;
      }

      // Return Per Cost rank badges column HTML
      const returnPerCostVal = fund.return_per_cost ? fund.return_per_cost.toFixed(1) : "N/A";
      const rankBadgeHtml = fund.return_per_cost_rank ? `<span class="rank-tag-badge">Rank #${fund.return_per_cost_rank}</span>` : "";
      const returnPerCostHtml = `${returnPerCostVal} ${rankBadgeHtml}`;

      // Determine score color text
      let scoreColor = "var(--color-down)";
      if (fund.composite_score > 65) scoreColor = "var(--color-up)";
      else if (fund.composite_score > 40) scoreColor = "#fbbf24";

      return `
        <tr>
          <td style="text-align: center; vertical-align: middle;">
            <input type="checkbox" class="compare-checkbox" data-code="${fund.scheme_code}" ${isChecked ? 'checked' : ''} style="cursor: pointer;">
          </td>
          <td>
            <div class="cell-bold">${fund.fund_name}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">${fund.fund_house}</div>
          </td>
          <td>
            <span class="category-tag ${badgeClass}">${fund.sub_category}</span>
          </td>
          <td class="numeric-cell cell-bold">${cagr3Y}</td>
          <td class="numeric-cell">${cagr1Y}</td>
          <td class="numeric-cell">${sharpe}</td>
          <td class="numeric-cell">${volatility}</td>
          <td class="numeric-cell" style="text-align: right; white-space: nowrap;">${starsHtml}</td>
          <td class="numeric-cell cell-bold" style="white-space: nowrap;">${returnPerCostHtml}</td>
          <td class="numeric-cell text-risk">${mdd}</td>
          <td class="numeric-cell score-cell-badge" style="color: ${scoreColor};">${fund.composite_score.toFixed(0)}</td>
        </tr>
      `;
    }).join('');

    // Attach checkbox events
    document.querySelectorAll(".compare-checkbox").forEach(chk => {
      chk.addEventListener("change", (e) => {
        const code = parseInt(e.target.dataset.code);
        if (e.target.checked) {
          if (selectedCompareCodes.length >= 3) {
            e.target.checked = false;
            alert("You can select a maximum of 3 funds to compare side-by-side.");
            return;
          }
          if (!selectedCompareCodes.includes(code)) {
            selectedCompareCodes.push(code);
          }
        } else {
          selectedCompareCodes = selectedCompareCodes.filter(c => c !== code);
        }
        updateCompareBar();
      });
    });
  }

  // --- FLOATING COMPARE BAR ---
  function updateCompareBar() {
    const bar = document.getElementById("compare-sticky-bar");
    const countSpan = document.getElementById("compare-count");
    const badgesContainer = document.getElementById("selected-funds-badges");

    countSpan.innerText = selectedCompareCodes.length;

    if (selectedCompareCodes.length > 0) {
      bar.classList.add("show");
      
      // Render badges
      badgesContainer.innerHTML = selectedCompareCodes.map(code => {
        const fund = fundMetrics.find(f => f.scheme_code === code);
        if (!fund) return "";
        return `
          <div class="drawer-tag">
            <span>${truncateString(fund.fund_name, 20)}</span>
            <i class="fa-solid fa-circle-xmark remove-fund-btn" data-code="${code}"></i>
          </div>
        `;
      }).join('');

      // Add tag remove event
      document.querySelectorAll(".remove-fund-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
          const code = parseInt(e.target.dataset.code);
          selectedCompareCodes = selectedCompareCodes.filter(c => c !== code);
          updateCompareBar();
          renderScreener(); // Synchronise checkboxes in the screener
        });
      });

    } else {
      bar.classList.remove("show");
    }
  }

  // --- COMPARISON PAGE RENDERER ---
  function renderComparison() {
    const emptyState = document.getElementById("compare-empty-state");
    const filledState = document.getElementById("compare-filled-state");
    const root = document.getElementById("compare-grid-root");

    if (selectedCompareCodes.length === 0) {
      emptyState.style.display = "block";
      filledState.style.display = "none";
      return;
    }

    emptyState.style.display = "none";
    filledState.style.display = "block";

    // Gather selected funds
    const funds = selectedCompareCodes.map(code => fundMetrics.find(f => f.scheme_code === code)).filter(Boolean);

    // Build comparison grid layout
    let html = `
      <!-- Labels Column -->
      <div class="comparison-column">
        <div class="comp-header label-cell">
          <h3 style="font-weight: 500;">Financial Metrics</h3>
          <p style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Side-by-Side Analysis</p>
        </div>
        <div class="comp-cell label-cell">AMC / House</div>
        <div class="comp-cell label-cell">Category</div>
        <div class="comp-cell label-cell">Composite Rank Score</div>
        <div class="comp-cell label-cell">CAGR (3-Year)</div>
        <div class="comp-cell label-cell">CAGR (1-Year)</div>
        <div class="comp-cell label-cell">Volatility (Annualised)</div>
        <div class="comp-cell label-cell">Sharpe Ratio</div>
        <div class="comp-cell label-cell">Sortino Ratio</div>
        <div class="comp-cell label-cell">Max Drawdown</div>
        <div class="comp-cell label-cell">Jensen's Alpha</div>
        <div class="comp-cell label-cell">Beta (Volatility Ratio)</div>
        <div class="comp-cell label-cell">Latest NAV</div>
        <div class="comp-cell label-cell">52W High / Low</div>
        <div class="comp-cell label-cell">Fund Age (Years)</div>
        <div class="comp-footer"></div>
      </div>
    `;

    // Add columns for each fund
    funds.forEach(fund => {
      const compositeColor = fund.composite_score > 65 ? "var(--color-up)" : (fund.composite_score > 40 ? "#fbbf24" : "var(--color-down)");

      html += `
        <div class="comparison-column">
          <div class="comp-header">
            <h3 title="${fund.fund_name}">${truncateString(fund.fund_name, 30)}</h3>
            <div>
              <span class="rank-badge" style="margin-top: 0.4rem;">Rank #${fund.universe_rank}</span>
            </div>
          </div>
          <div class="comp-cell" style="font-size: 0.75rem; color: var(--text-secondary);">${fund.fund_house}</div>
          <div class="comp-cell" style="font-size: 0.75rem; color: var(--text-secondary);">${fund.sub_category}</div>
          <div class="comp-cell" style="font-weight: 600; color: ${compositeColor}; font-size: 1rem;">
            ${fund.composite_score.toFixed(0)} <span style="font-size: 0.75rem; font-weight: normal; color: var(--text-muted);">/ 100</span>
          </div>
          <div class="comp-cell cell-bold ${fund.cagr_3y >= 0 ? 'text-profit' : 'text-risk'}">${fund.cagr_3y !== null ? fund.cagr_3y.toFixed(1) + '%' : 'N/A'}</div>
          <div class="comp-cell ${fund.cagr_1y >= 0 ? 'text-profit' : 'text-risk'}">${fund.cagr_1y !== null ? fund.cagr_1y.toFixed(1) + '%' : 'N/A'}</div>
          <div class="comp-cell">${fund.volatility_pct !== null ? fund.volatility_pct.toFixed(2) + '%' : 'N/A'}</div>
          <div class="comp-cell cell-bold">${fund.sharpe_ratio !== null ? fund.sharpe_ratio.toFixed(2) : 'N/A'}</div>
          <div class="comp-cell">${fund.sortino_ratio !== null ? fund.sortino_ratio.toFixed(2) : 'N/A'}</div>
          <div class="comp-cell text-risk">${fund.max_drawdown_pct !== null ? fund.max_drawdown_pct.toFixed(2) + '%' : 'N/A'}</div>
          <div class="comp-cell ${fund.alpha_pct >= 0 ? 'text-profit' : 'text-risk'}">${fund.alpha_pct !== null ? (fund.alpha_pct > 0 ? '+' : '') + fund.alpha_pct.toFixed(2) + '%' : 'N/A'}</div>
          <div class="comp-cell">${fund.beta !== null ? fund.beta.toFixed(2) : 'N/A'}</div>
          <div class="comp-cell cell-bold">₹${fund.latest_nav.toFixed(2)}</div>
          <div class="comp-cell" style="font-size: 0.75rem; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 2px;">
            <span class="text-profit">H: ₹${fund.nav_52w_high.toFixed(1)}</span>
            <span class="text-risk">L: ₹${fund.nav_52w_low.toFixed(1)}</span>
          </div>
          <div class="comp-cell">${fund.fund_age_years.toFixed(1)} Yrs</div>
          <div class="comp-footer">
            <button class="btn-flat btn-flat-secondary remove-compare-column-btn" data-code="${fund.scheme_code}" style="padding: 0.3rem 0.6rem; font-size: 0.7rem;">
              Remove
            </button>
          </div>
        </div>
      `;
    });

    root.innerHTML = html;

    // Attach remove buttons inside grid footer
    document.querySelectorAll(".remove-compare-column-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const code = parseInt(e.target.dataset.code);
        selectedCompareCodes = selectedCompareCodes.filter(c => c !== code);
        updateCompareBar();
        renderScreener();
        renderComparison();
      });
    });
  }

  // --- ROLLING RETURNS SELECTORS ---
  function renderRollingSelectors() {
    const container = document.getElementById("rolling-selectors-container");
    if (fundMetrics.length === 0) return;

    container.innerHTML = fundMetrics.map(fund => {
      const isSelected = selectedRollingCodes.includes(fund.scheme_code);
      return `
        <button class="selector-pill ${isSelected ? 'active' : ''}" data-code="${fund.scheme_code}">
          ${truncateString(fund.fund_name, 22)}
        </button>
      `;
    }).join('');

    // Attach selector toggle events
    document.querySelectorAll(".selector-pill").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const code = parseInt(e.currentTarget.dataset.code);
        if (selectedRollingCodes.includes(code)) {
          if (selectedRollingCodes.length <= 1) return; // Keep at least one
          selectedRollingCodes = selectedRollingCodes.filter(c => c !== code);
        } else {
          if (selectedRollingCodes.length >= 5) {
            alert("Select up to 5 funds to display on the rolling returns chart.");
            return;
          }
          selectedRollingCodes.push(code);
        }
        
        renderRollingSelectors();
        updateRollingReturnsChart();
      });
    });
  }

  // --- CHARTS SYSTEM (CHART.JS CONFIG) ---
  function initGlobalChartDefaults() {
    Chart.defaults.color = '#71717a'; // text-muted
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)';
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(9, 9, 11, 0.95)';
    Chart.defaults.plugins.tooltip.titleColor = '#fff';
    Chart.defaults.plugins.tooltip.bodyColor = '#e4e4e7';
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.08)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 6;
  }

  function renderCharts() {
    if (fundMetrics.length === 0) return;

    initGlobalChartDefaults();
    
    // 1. Risk vs Return Scatter Plot
    renderRiskReturnScatter();

    // 2. AUM Bar Chart
    renderAUMDistribution();

    // 3. Rolling Returns Line Chart
    updateRollingReturnsChart();
  }

  // Helper to convert hex colors to transparent rgba colors for glassy styling
  function hexToRgbA(hex, alpha = 1) {
    let c;
    if (/^#([A-Fa-f0-9]{3}){1,2}$/.test(hex)) {
      c = hex.substring(1).split('');
      if (c.length === 3) {
        c = [c[0], c[0], c[1], c[1], c[2], c[2]];
      }
      c = '0x' + c.join('');
      return `rgba(${[(c >> 16) & 255, (c >> 8) & 255, c & 255].join(',')},${alpha})`;
    }
    return hex;
  }

  // Visual 1: Risk vs. Return Profile (3Y CAGR vs Volatility)
  function renderRiskReturnScatter() {
    const ctx = document.getElementById("riskReturnChart").getContext("2d");
    
    if (riskReturnChartInstance) {
      riskReturnChartInstance.destroy();
    }

    const scatterData = fundMetrics
      .filter(f => f.volatility_pct !== null && f.cagr_3y !== null)
      .map(f => {
        const theme = getCategoryTheme(f.broad_category);
        
        // Performance square root scale based on AUM
        let radius = 6;
        if (f.aum_cr) {
          radius = 6 + (Math.sqrt(f.aum_cr) * 0.13);
        }
        
        return {
          x: f.volatility_pct,
          y: f.cagr_3y,
          label: f.fund_name,
          category: f.broad_category,
          subCategory: f.sub_category,
          sharpe: f.sharpe_ratio,
          score: f.composite_score,
          aum: f.aum_cr,
          radius: radius,
          color: theme.color
        };
      })
      .sort((a, b) => (b.aum || 0) - (a.aum || 0)); // Sort AUM descending (larger bubbles drawn first in background)

    riskReturnChartInstance = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [{
          data: scatterData,
          backgroundColor: scatterData.map(d => hexToRgbA(d.color, 0.45)), // Glassy transparent fill
          borderColor: scatterData.map(d => d.color), // Solid glow category border
          borderWidth: 1.5,
          pointRadius: scatterData.map(d => d.radius),
          pointHoverRadius: scatterData.map(d => d.radius + 3),
          hoverBorderColor: '#fafafa', // Highly defined hover outline
          hoverBorderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => {
                const item = context.raw;
                return [
                  `Fund: ${item.label}`,
                  `Category: ${item.subCategory}`,
                  `Risk (Vol): ${item.x.toFixed(1)}%`,
                  `Return (CAGR 3Y): ${item.y.toFixed(1)}%`,
                  `AUM: ₹${item.aum ? item.aum.toLocaleString('en-IN') : 'N/A'} Cr`,
                  `Sharpe Ratio: ${item.sharpe.toFixed(2)}`,
                  `Score: ${item.score.toFixed(0)}`
                ];
              }
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'Volatility (Annualised Risk %)',
              color: '#a1a1aa'
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          },
          y: {
            title: {
              display: true,
              text: '3-Year CAGR (Return %)',
              color: '#a1a1aa'
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          }
        }
      }
    });
  }

  // Visual 2: Category AUM Distribution Bar Chart
  function renderAUMDistribution() {
    const ctx = document.getElementById("aumDistributionChart").getContext("2d");

    if (aumChartInstance) {
      aumChartInstance.destroy();
    }

    const aumData = categoryAUM.filter(d => 
      d.scheme_name && 
      !d.scheme_name.toLowerCase().includes("sub total") && 
      !d.scheme_name.toLowerCase().includes("grand total") &&
      !d.scheme_name.toLowerCase().includes("total")
    ).sort((a, b) => b.aum_cr - a.aum_cr).slice(0, 6);

    const labels = aumData.map(d => truncateString(d.scheme_name, 16));
    const values = aumData.map(d => d.aum_cr / 1000); // Convert to Thousands of Cr

    aumChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            'rgba(34, 211, 238, 0.75)',  // Muted Cyan
            'rgba(129, 140, 248, 0.75)', // Muted Indigo
            'rgba(96, 165, 250, 0.75)',  // Muted Blue
            'rgba(251, 191, 36, 0.75)',  // Muted Amber
            'rgba(168, 85, 247, 0.75)',  // Muted Purple
            'rgba(244, 63, 94, 0.75)'    // Muted Rose
          ],
          borderRadius: 4,
          borderWidth: 0,
          barThickness: 14
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y', // Horizontal bars
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => ` AUM: ₹${(context.raw).toFixed(1)}k Cr`
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'AUM (₹ Thousand Crore)',
              color: '#a1a1aa'
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          },
          y: {
            grid: { display: false }
          }
        }
      }
    });
  }

  // Visual 3: Rolling 1-Year Returns Line Chart
  function updateRollingReturnsChart() {
    const ctx = document.getElementById("rollingReturnsChart").getContext("2d");

    if (rollingReturnsChartInstance) {
      rollingReturnsChartInstance.destroy();
    }

    if (rollingReturns.length === 0 || selectedRollingCodes.length === 0) return;

    const datasets = selectedRollingCodes.map(code => {
      const fund = fundMetrics.find(f => f.scheme_code === code);
      if (!fund) return null;

      const theme = getCategoryTheme(fund.broad_category);
      
      const fundRolling = rollingReturns
        .filter(r => r.scheme_code === code)
        .sort((a, b) => new Date(a.date) - new Date(b.date));

      const points = fundRolling.map(r => ({
        x: new Date(r.date),
        y: r.rolling_1y_return_pct
      }));

      return {
        label: truncateString(fund.fund_name, 22),
        data: points,
        borderColor: theme.color,
        backgroundColor: theme.bg,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: false,
        tension: 0.1
      };
    }).filter(Boolean);

    rollingReturnsChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 10,
              usePointStyle: true,
              color: '#a1a1aa'
            }
          },
          tooltip: {
            callbacks: {
              title: (context) => {
                const date = new Date(context[0].parsed.x);
                return date.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
              },
              label: (context) => {
                return ` ${context.dataset.label}: ${context.parsed.y.toFixed(2)}%`;
              }
            }
          }
        },
        scales: {
          x: {
            type: 'time',
            time: {
              parser: 'yyyy-MM-dd',
              unit: 'month',
              displayFormats: { month: 'MMM yy' }
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          },
          y: {
            title: {
              display: true,
              text: '1Y Rolling Return %',
              color: '#a1a1aa'
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          }
        }
      }
    });
  }

  // --- SPA VIEW ROUTING ---
  function switchPage(pageId) {
    // Switch navigation link states
    document.querySelectorAll(".tab-btn").forEach(btn => {
      if (btn.dataset.page === pageId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    // Toggle active sections
    document.querySelectorAll(".page-section").forEach(page => {
      if (page.id === `${pageId}-page`) {
        page.classList.add("active");
      } else {
        page.classList.remove("active");
      }
    });

    // Trigger page-specific loads
    if (pageId === "visuals") {
      setTimeout(renderCharts, 100);
    } else if (pageId === "compare") {
      renderComparison();
    } else if (pageId === "deepdive") {
      setTimeout(renderDeepDive, 100);
    }
  }

  // --- INTERACTION CONTROLS ---

  // Top Nav Tab Clicks
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const pageId = e.currentTarget.dataset.page;
      switchPage(pageId);
    });
  });

  // Table Column Header Click Sorting Setup
  function setupTableSorting() {
    const headers = document.querySelectorAll("#screener-table th.sortable");
    headers.forEach(header => {
      header.addEventListener("click", () => {
        const sortKey = header.dataset.sort;
        if (activeSortColumn === sortKey) {
          activeSortDirection = activeSortDirection === "asc" ? "desc" : "asc";
        } else {
          activeSortColumn = sortKey;
          // Default lower-is-better metrics to asc, others to desc
          if (sortKey === "volatility_pct" || sortKey === "max_drawdown_pct") {
            activeSortDirection = "asc";
          } else {
            activeSortDirection = "desc";
          }
        }
        updateSortHeaderClasses();
        renderScreener();
      });
    });
  }

  function updateSortHeaderClasses() {
    const headers = document.querySelectorAll("#screener-table th.sortable");
    headers.forEach(header => {
      const sortKey = header.dataset.sort;
      if (sortKey === activeSortColumn) {
        header.classList.add("active");
        header.classList.remove("asc", "desc");
        header.classList.add(activeSortDirection);
      } else {
        header.classList.remove("active", "asc", "desc");
      }
    });
  }

  // Category Filtering Dropdown
  document.getElementById("category-select").addEventListener("change", (e) => {
    activeCategory = e.target.value;
    renderScreener();
  });

  // AMC Select Change
  document.getElementById("amc-select").addEventListener("change", (e) => {
    activeAMC = e.target.value;
    renderScreener();
  });

  // Search Input Input
  document.getElementById("scheme-search").addEventListener("input", (e) => {
    activeSearch = e.target.value;
    renderScreener();
  });

  // Expense Ratio Select Change
  const expenseSelect = document.getElementById("expense-select");
  if (expenseSelect) {
    expenseSelect.addEventListener("change", (e) => {
      activeMaxExpense = e.target.value;
      renderScreener();
    });
  }

  // Min AUM Select Change
  const aumSelect = document.getElementById("aum-filter-select");
  if (aumSelect) {
    aumSelect.addEventListener("change", (e) => {
      activeMinAUM = e.target.value;
      renderScreener();
    });
  }

  // Stars Rating Select Change
  const starsSelect = document.getElementById("stars-select");
  if (starsSelect) {
    starsSelect.addEventListener("change", (e) => {
      activeMinStars = e.target.value;
      renderScreener();
    });
  }

  // Sticky Compare Bar Actions
  document.getElementById("clear-compare-btn").addEventListener("click", () => {
    selectedCompareCodes = [];
    updateCompareBar();
    renderScreener();
  });

  document.getElementById("trigger-compare-btn").addEventListener("click", () => {
    switchPage("compare");
  });

  // Sync Data Button
  const syncBtn = document.getElementById("sync-data-btn");
  if (syncBtn) {
    syncBtn.addEventListener("click", async () => {
      const icon = syncBtn.querySelector("i");
      const textSpan = syncBtn.querySelector("span");
      
      icon.classList.add("fa-spin");
      textSpan.innerText = "Syncing...";
      syncBtn.disabled = true;

      try {
        const res = await fetch("/run-pipeline", { method: "POST" });
        if (res.ok) {
          alert("AMFI data sync completed successfully! Reloading dashboard...");
          await loadData();
        } else {
          const errData = await res.json();
          console.error("Pipeline failure details:", errData);
          alert("Failed to sync data: " + (errData.message || "Pipeline error"));
        }
      } catch (e) {
        console.error("POST connection error:", e);
        alert("Failed to connect to local server endpoint. Make sure python run_dashboard.py is running.");
      } finally {
        icon.classList.remove("fa-spin");
        textSpan.innerText = "Sync Data";
        syncBtn.disabled = false;
      }
    });
  }

  // --- POWER BI EMBED CONTROLLER ---
  const pbiInput = document.getElementById("pbi-embed-url");
  const pbiSaveBtn = document.getElementById("pbi-embed-save-btn");
  const pbiClearBtn = document.getElementById("pbi-embed-clear-btn");
  const pbiIframeWrapper = document.getElementById("pbi-iframe-wrapper");
  const pbiIframe = document.getElementById("pbi-iframe");
  const pbiPlaceholder = document.getElementById("pbi-placeholder-card");

  function loadPowerBI() {
    const savedUrl = localStorage.getItem("pbi_embed_url");
    if (savedUrl) {
      let embedSrc = savedUrl.trim();
      if (embedSrc.startsWith("<iframe")) {
        const match = embedSrc.match(/src=["']([^"']+)["']/);
        if (match && match[1]) {
          embedSrc = match[1];
        }
      }
      pbiIframe.src = embedSrc;
      pbiIframeWrapper.style.display = "flex";
      pbiPlaceholder.style.display = "none";
      if (pbiInput) pbiInput.value = savedUrl;
    } else {
      pbiIframe.src = "";
      pbiIframeWrapper.style.display = "none";
      pbiPlaceholder.style.display = "flex";
      if (pbiInput) pbiInput.value = "";
    }
  }

  if (pbiSaveBtn) {
    pbiSaveBtn.addEventListener("click", () => {
      const urlValue = pbiInput.value.trim();
      if (urlValue) {
        localStorage.setItem("pbi_embed_url", urlValue);
        loadPowerBI();
      } else {
        alert("Please enter a valid Power BI Embed URL or iframe code.");
      }
    });
  }

  if (pbiClearBtn) {
    pbiClearBtn.addEventListener("click", () => {
      localStorage.removeItem("pbi_embed_url");
      loadPowerBI();
    });
  }

  // Load initially
  loadPowerBI();

  // Empty State Button Redirect
  const goToScreenerBtn = document.getElementById("go-to-screener-btn");
  if (goToScreenerBtn) {
    goToScreenerBtn.addEventListener("click", () => {
      switchPage("screener");
    });
  }

  // Set up sorting triggers
  setupTableSorting();

  // --- BACKGROUND POLLING FOR LIVE UPDATES ---
  function startAutoRefreshPoll() {
    setInterval(async () => {
      try {
        const timestamp = Date.now();
        // Send a lightweight HEAD request to bypass browser cache and check headers
        const res = await fetch(`data/output/fund_metrics.csv?t=${timestamp}`, {
          method: "HEAD"
        });
        
        if (res.ok) {
          const newModifiedTime = res.headers.get("Last-Modified");
          // If we have a previously saved time and it has changed, trigger refresh
          if (newModifiedTime && lastKnownModifiedTime && newModifiedTime !== lastKnownModifiedTime) {
            console.log(`[AutoRefresh] Detected data file modification (Old: ${lastKnownModifiedTime}, New: ${newModifiedTime}). Reloading...`);
            lastKnownModifiedTime = newModifiedTime;
            await loadData();
          }
        }
      } catch (err) {
        console.warn("[AutoRefresh] Failed to poll server for updates:", err);
      }
    }, 5000); // Poll every 5 seconds
  }

  // --- DEEP DIVE SYSTEM ---
  
  function populateDeepdiveSelector() {
    const select = document.getElementById("deepdive-scheme-select");
    if (!select || fundMetrics.length === 0) return;
    
    select.innerHTML = fundMetrics.map(fund => `
      <option value="${fund.scheme_code}" ${fund.scheme_code === activeDeepdiveCode ? 'selected' : ''}>
        ${fund.fund_name}
      </option>
    `).join('');
    
    // Attach selector change listener
    select.addEventListener("change", (e) => {
      activeDeepdiveCode = parseInt(e.target.value);
      renderDeepDive();
    });
  }
  
  function renderDeepDive() {
    if (fundMetrics.length === 0 || !activeDeepdiveCode) return;
    
    // 1. Draw AUM Trend Bar Chart
    updateDeepdiveAumChart();
    
    // 2. Initialise and run the Cost Impact Calculator
    updateCostImpactCalculator();
  }
  
  function updateDeepdiveAumChart() {
    const ctx = document.getElementById("deepdiveAumChart");
    if (!ctx) return;
    
    if (deepdiveAumChartInstance) {
      deepdiveAumChartInstance.destroy();
    }
    
    const fund = fundMetrics.find(f => f.scheme_code === activeDeepdiveCode);
    if (!fund) return;
    
    // Filter history for the active fund and sort chronologically
    const history = fundAumHistory
      .filter(h => h.scheme_code === activeDeepdiveCode)
      .sort((a, b) => new Date(a.date) - new Date(b.date));
      
    if (history.length === 0) {
      // Fallback: If no history, render single bar representing current AUM
      history.push({
        date: new Date().toISOString().slice(0, 10),
        aum_cr: fund.aum_cr || 0
      });
    }
    
    const labels = history.map(h => {
      const date = new Date(h.date);
      return date.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
    });
    
    const dataValues = history.map(h => h.aum_cr);
    
    deepdiveAumChartInstance = new Chart(ctx.getContext("2d"), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'AUM (₹ Crore)',
          data: dataValues,
          backgroundColor: 'rgba(34, 211, 238, 0.65)', // Cyan glow
          hoverBackgroundColor: 'rgba(34, 211, 238, 0.95)',
          borderRadius: 4,
          borderWidth: 0,
          barThickness: 18
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => ` AUM: ₹${context.raw.toLocaleString('en-IN')} Cr`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false }
          },
          y: {
            title: {
              display: true,
              text: 'AUM (₹ Crore)',
              color: '#a1a1aa'
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          }
        }
      }
    });
  }

  function updateCostImpactCalculator() {
    const fund = fundMetrics.find(f => f.scheme_code === activeDeepdiveCode);
    if (!fund) return;
    
    const ter = fund.expense_ratio_pct || 0.50; // Default fallback to 0.50% if missing
    
    // Sliders
    const sipSlider = document.getElementById("calc-sip-slider");
    const cagrSlider = document.getElementById("calc-cagr-slider");
    const periodSlider = document.getElementById("calc-period-slider");
    
    // Outputs
    const sipValLabel = document.getElementById("calc-sip-val");
    const cagrValLabel = document.getElementById("calc-cagr-val");
    const periodValLabel = document.getElementById("calc-period-val");
    
    const grossOutputLabel = document.getElementById("calc-gross-output");
    const netOutputLabel = document.getElementById("calc-net-output");
    const dragOutputLabel = document.getElementById("calc-drag-output");
    
    if (!sipSlider || !cagrSlider || !periodSlider) return;
    
    // Wealth computation logic
    const recalculateCalculator = () => {
      const sip = parseFloat(sipSlider.value);
      const cagr = parseFloat(cagrSlider.value) / 100;
      const years = parseInt(periodSlider.value);
      
      // Update displays
      sipValLabel.innerText = `₹${sip.toLocaleString('en-IN')}`;
      cagrValLabel.innerText = `${(cagr * 100).toFixed(1)}%`;
      periodValLabel.innerText = `${years} Years`;
      
      // Wealth computation formulas
      const r_gross = cagr / 12;
      const r_net = (cagr - (ter / 100)) / 12;
      const n_months = years * 12;
      
      let grossWealth = 0;
      let netWealth = 0;
      
      if (r_gross > 0) {
        grossWealth = sip * ((Math.pow(1 + r_gross, n_months) - 1) / r_gross) * (1 + r_gross);
      } else {
        grossWealth = sip * n_months;
      }
      
      if (r_net > 0) {
        netWealth = sip * ((Math.pow(1 + r_net, n_months) - 1) / r_net) * (1 + r_net);
      } else {
        netWealth = sip * n_months;
      }
      
      const terDrag = grossWealth - netWealth;
      
      const formatRupees = (num) => {
        const lakhs = num / 100000;
        if (lakhs >= 100) {
          return `₹${(lakhs / 100).toFixed(2)} Cr`;
        }
        return `₹${lakhs.toFixed(2)} Lakhs`;
      };
      
      grossOutputLabel.innerText = formatRupees(grossWealth);
      netOutputLabel.innerText = formatRupees(netWealth);
      dragOutputLabel.innerText = formatRupees(terDrag);
      
      updateCalculatorLineChart(sip, cagr, ter, years);
    };
    
    // Attach listeners
    sipSlider.oninput = recalculateCalculator;
    cagrSlider.oninput = recalculateCalculator;
    periodSlider.oninput = recalculateCalculator;
    
    recalculateCalculator();
  }
  
  function updateCalculatorLineChart(sip, cagr, ter, years) {
    const ctx = document.getElementById("costCalculatorChart");
    if (!ctx) return;
    
    if (costCalculatorChartInstance) {
      costCalculatorChartInstance.destroy();
    }
    
    const yearsLabels = [];
    const grossData = [];
    const netData = [];
    
    for (let y = 0; y <= years; y++) {
      yearsLabels.push(`Yr ${y}`);
      if (y === 0) {
        grossData.push(0);
        netData.push(0);
        continue;
      }
      
      const r_gross = cagr / 12;
      const r_net = (cagr - (ter / 100)) / 12;
      const n_months = y * 12;
      
      let gw = 0;
      let nw = 0;
      
      if (r_gross > 0) {
        gw = sip * ((Math.pow(1 + r_gross, n_months) - 1) / r_gross) * (1 + r_gross);
      } else {
        gw = sip * n_months;
      }
      
      if (r_net > 0) {
        nw = sip * ((Math.pow(1 + r_net, n_months) - 1) / r_net) * (1 + r_net);
      } else {
        nw = sip * n_months;
      }
      
      grossData.push(Math.round(gw));
      netData.push(Math.round(nw));
    }
    
    costCalculatorChartInstance = new Chart(ctx.getContext("2d"), {
      type: 'line',
      data: {
        labels: yearsLabels,
        datasets: [
          {
            label: 'Gross Growth (No Fees)',
            data: grossData,
            borderColor: '#22d3ee', // Cyan
            backgroundColor: 'rgba(34, 211, 238, 0.04)',
            borderWidth: 1.8,
            pointRadius: 0,
            pointHoverRadius: 4,
            fill: true,
            tension: 0.15
          },
          {
            label: 'Net Growth (With Fees)',
            data: netData,
            borderColor: '#60a5fa', // Blue
            backgroundColor: 'rgba(96, 165, 250, 0.04)',
            borderWidth: 1.8,
            pointRadius: 0,
            pointHoverRadius: 4,
            fill: true,
            tension: 0.15
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 8,
              usePointStyle: true,
              color: '#a1a1aa',
              font: { size: 9 }
            }
          },
          tooltip: {
            callbacks: {
              label: (context) => ` ${context.dataset.label}: ₹${context.raw.toLocaleString('en-IN')}`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { size: 9 } }
          },
          y: {
            ticks: {
              font: { size: 9 },
              callback: (value) => `₹${(value / 100000).toFixed(1)}L`
            },
            grid: { color: 'rgba(255, 255, 255, 0.03)' }
          }
        }
      }
    });
  }

  // Load Time Scales Support in ChartJS
  if (!Chart.adapters || !Chart.adapters._date) {
    const timeAdapterScript = document.createElement("script");
    timeAdapterScript.src = "https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns";
    timeAdapterScript.onload = async () => {
      await loadData();
      startAutoRefreshPoll();
    };
    document.head.appendChild(timeAdapterScript);
  } else {
    loadData().then(() => {
      startAutoRefreshPoll();
    });
  }

});
