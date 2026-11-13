const state = {
  filings: [],
  selectedAccession: null,
  selectedFiling: null,
};

const elements = {
  loading: document.getElementById('loading'),
  kpiGrid: document.getElementById('kpiGrid'),
  filingsTableBody: document.getElementById('filingsTableBody'),
  filingCountBadge: document.getElementById('filingCountBadge'),
  selectedDetails: document.getElementById('selectedDetails'),
  scoreSummary: document.getElementById('scoreSummary'),
  scoreAction: document.getElementById('scoreAction'),
  refreshBtn: document.getElementById('refreshBtn'),
};

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body}`);
  }
  return response.json();
}

function setKpis(health, filings) {
  const cards = [
    {
      label: 'Environment',
      value: (health.app_env || 'LOCAL').toUpperCase(),
      subtext: 'Deterministic audit sandbox',
      tone: 'bg-slate-900 text-white',
    },
    {
      label: 'Database',
      value: health.database === 'connected' ? 'ONLINE' : 'OFFLINE',
      subtext: health.database === 'connected' ? 'SQLite connection healthy' : 'Check connection',
      tone: health.database === 'connected' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700',
    },
    {
      label: 'Filings',
      value: String(filings.length),
      subtext: 'Recent SEC 10-K records',
      tone: 'bg-blue-50 text-blue-700',
    },
    {
      label: 'API',
      value: health.status === 'healthy' ? 'READY' : 'DEGRADED',
      subtext: `Version ${health.version || '0.1.0'}`,
      tone: health.status === 'healthy' ? 'bg-indigo-50 text-indigo-700' : 'bg-amber-50 text-amber-700',
    },
  ];

  elements.kpiGrid.innerHTML = cards
    .map(
      (card) => `
        <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft transition hover:-translate-y-0.5 hover:shadow-lg">
          <div class="flex items-center justify-between gap-2">
            <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">${card.label}</p>
            <span class="rounded-full px-2 py-1 text-[10px] font-semibold ${card.tone}">${card.value}</span>
          </div>
          <div class="mt-4 text-2xl font-bold text-slate-900">${card.value}</div>
          <p class="mt-1 text-sm text-slate-500">${card.subtext}</p>
        </div>
      `,
    )
    .join('');

  elements.kpiGrid.classList.remove('hidden');
  elements.loading.classList.add('hidden');
}

function renderFilings(filings) {
  state.filings = filings;
  elements.filingCountBadge.textContent = `${filings.length} records`;

  if (!filings.length) {
    elements.filingsTableBody.innerHTML = `
      <tr>
        <td colspan="5" class="px-4 py-8 text-center text-slate-500">No filings available yet.</td>
      </tr>
    `;
    return;
  }

  elements.filingsTableBody.innerHTML = filings
    .map(
      (filing) => `
        <tr class="align-middle hover:bg-slate-50">
          <td class="px-4 py-3 font-semibold text-slate-800">${filing.company_name || 'Unknown company'}</td>
          <td class="px-4 py-3 text-slate-600">${filing.ticker || '—'}</td>
          <td class="px-4 py-3 text-slate-600">${filing.form_type || '—'}</td>
          <td class="px-4 py-3 text-slate-600">${filing.filing_date || '—'}</td>
          <td class="px-4 py-3 text-right">
            <button
              class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700"
              data-accession="${filing.accession_number}"
            >
              Select
            </button>
          </td>
        </tr>
      `,
    )
    .join('');

  elements.filingsTableBody.querySelectorAll('button[data-accession]').forEach((button) => {
    button.addEventListener('click', () => {
      const accession = button.dataset.accession;
      selectFiling(accession);
    });
  });
}

function renderSelectedFiling(filing) {
  if (!filing) {
    elements.selectedDetails.innerHTML = '<p>Select a filing to inspect details and score it.</p>';
    elements.scoreAction.classList.add('hidden');
    return;
  }

  state.selectedFiling = filing;
  state.selectedAccession = filing.accession_number;
  elements.selectedDetails.innerHTML = `
    <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Company</p>
      <h3 class="mt-2 text-lg font-semibold text-slate-900">${filing.company_name || 'Unknown company'}</h3>
      <div class="mt-3 grid gap-2 text-sm text-slate-600">
        <div><span class="font-medium text-slate-700">Ticker:</span> ${filing.ticker || '—'}</div>
        <div><span class="font-medium text-slate-700">CIK:</span> ${filing.cik || '—'}</div>
        <div><span class="font-medium text-slate-700">Form:</span> ${filing.form_type || '—'}</div>
        <div><span class="font-medium text-slate-700">Filing date:</span> ${filing.filing_date || '—'}</div>
        <div><span class="font-medium text-slate-700">Accession:</span> ${filing.accession_number || '—'}</div>
      </div>
    </div>
  `;

  elements.scoreAction.classList.remove('hidden');
}

async function loadScore(accession) {
  const scoreSummary = document.getElementById('scoreSummary');
  scoreSummary.textContent = 'Loading score...';
  scoreSummary.className = 'mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800';

  try {
    const score = await fetchJson(`/metrics/score/${encodeURIComponent(accession)}`);
    const status = score.overall_status || 'UNKNOWN';
    const quality = score.quality_score_100 ?? 0;
    const overall = score.overall_score ?? 0;
    const metricsCount = score.metrics?.length || 0;

    scoreSummary.innerHTML = `
      <div class="space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">Summary</p>
            <h3 class="mt-1 text-lg font-semibold text-slate-900">${status}</h3>
          </div>
          <span class="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">${quality.toFixed(1)} / 100</span>
        </div>
        <div class="grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl bg-slate-100 p-3">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Overall score</p>
            <p class="mt-2 text-2xl font-bold text-slate-900">${Number(overall).toFixed(3)}</p>
          </div>
          <div class="rounded-xl bg-slate-100 p-3">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Metrics</p>
            <p class="mt-2 text-2xl font-bold text-slate-900">${metricsCount}</p>
          </div>
          <div class="rounded-xl bg-slate-100 p-3">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Review category</p>
            <p class="mt-2 text-lg font-bold text-slate-900">${score.overall_review_category || 'N/A'}</p>
          </div>
        </div>
        <p class="text-slate-600">${score.summary_explanation || 'Deterministic scoring completed.'}</p>
      </div>
    `;
  } catch (error) {
    try {
      const response = await fetch(`/metrics/score/${encodeURIComponent(accession)}`, { method: 'POST' });
      if (!response.ok) {
        throw new Error('Unable to generate score');
      }
      const score = await response.json();
      const status = score.overall_status || 'UNKNOWN';
      const quality = score.quality_score_100 ?? 0;
      const overall = score.overall_score ?? 0;
      const metricsCount = score.metrics?.length || 0;

      scoreSummary.innerHTML = `
        <div class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">Summary</p>
              <h3 class="mt-1 text-lg font-semibold text-slate-900">${status}</h3>
            </div>
            <span class="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">${quality.toFixed(1)} / 100</span>
          </div>
          <div class="grid gap-3 sm:grid-cols-3">
            <div class="rounded-xl bg-slate-100 p-3">
              <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Overall score</p>
              <p class="mt-2 text-2xl font-bold text-slate-900">${Number(overall).toFixed(3)}</p>
            </div>
            <div class="rounded-xl bg-slate-100 p-3">
              <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Metrics</p>
              <p class="mt-2 text-2xl font-bold text-slate-900">${metricsCount}</p>
            </div>
            <div class="rounded-xl bg-slate-100 p-3">
              <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Review category</p>
              <p class="mt-2 text-lg font-bold text-slate-900">${score.overall_review_category || 'N/A'}</p>
            </div>
          </div>
          <p class="text-slate-600">${score.summary_explanation || 'Deterministic scoring completed.'}</p>
        </div>
      `;
    } catch (fallbackError) {
      scoreSummary.className = 'mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800';
      scoreSummary.textContent = `Unable to load score for ${accession}. ${fallbackError.message}`;
    }
  }
}

function selectFiling(accession) {
  const filing = state.filings.find((item) => item.accession_number === accession);
  renderSelectedFiling(filing);
  if (filing) {
    loadScore(filing.accession_number);
  }
}

async function loadDashboard() {
  try {
    const [health, filings] = await Promise.all([
      fetchJson('/health'),
      fetchJson('/filings?limit=20'),
    ]);

    setKpis(health, filings);
    renderFilings(filings);

    if (filings.length) {
      selectFiling(filings[0].accession_number);
    }
  } catch (error) {
    elements.kpiGrid.innerHTML = `
      <div class="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-700 sm:col-span-2 xl:col-span-4">
        Unable to load dashboard data: ${error.message}
      </div>
    `;
    elements.kpiGrid.classList.remove('hidden');
    elements.loading.classList.add('hidden');
  }
}

elements.scoreAction.addEventListener('click', () => {
  if (state.selectedAccession) {
    loadScore(state.selectedAccession);
  }
});

elements.refreshBtn.addEventListener('click', () => {
  elements.loading.classList.remove('hidden');
  elements.kpiGrid.classList.add('hidden');
  loadDashboard();
});

loadDashboard();
