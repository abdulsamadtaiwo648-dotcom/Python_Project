import sys
import re

with open('C:\\Users\\HP\\Python_Project\\templates\\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace style block
style_replacement = """<style>
        body { 
          font-family: 'Inter', sans-serif; 
          background: #000000;
          color: #f1f5f9;
        }

        /* ── Stat Cards: fluid number sizing ── */
        .stat-value {
            font-size: clamp(0.55rem, 3.2vw, 1.1rem);
            font-weight: 800;
            line-height: 1.2;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: block;
            max-width: 100%;
        }
        @media (min-width: 640px) {
            .stat-value { font-size: 1.2rem; }
        }

        .big-total-value {
            font-size: clamp(1.25rem, 7vw, 2.5rem);
            font-weight: 800;
            line-height: 1.1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: block;
            width: 100%;
        }
        @media (min-width: 640px) {
            .big-total-value { font-size: 2.5rem; }
        }

        /* Business card */
        .biz-card {
            background: #0f172a;
            border-radius: 16px;
            position: relative;
            overflow: hidden;
            font-family: 'Inter', sans-serif;
            border: 1px solid #1e293b;
            box-shadow: 0 10px 40px rgba(99,102,241,0.15), 0 2px 8px rgba(0,0,0,0.4);
        }
        .biz-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 5px;
            background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 60%, #c084fc 100%);
            border-radius: 16px 16px 0 0;
        }
        .biz-card-divider {
            border: none;
            height: 1px;
            background: #1e293b;
            margin: 10px 0;
        }
        .custom-select-menu {
            max-height: 16rem;
            overflow-y: auto;
            scrollbar-width: thin;
            background: #1e293b;
            border: 1px solid #374151;
            border-radius: 12px;
        }
        .custom-select-option[aria-selected="true"] {
            background: #1e1b4b;
            color: #a5b4fc;
            font-weight: 700;
        }

        /* Dark inputs */
        input, select, textarea {
            background-color: #1a1a2e !important;
            color: #e2e8f0 !important;
            border-color: #374151 !important;
        }
        input::placeholder, textarea::placeholder {
            color: #6b7280 !important;
        }
        select option {
            background: #1e293b;
            color: #e2e8f0;
        }

        /* Mobile: hide old nav, show bottom bar */
        @media (max-width: 1023px) {
            html, body {
                width: 100%;
                max-width: 100%;
                overflow-x: hidden;
                padding-bottom: 64px;
            }
            .desktop-dashboard-shell {
                display: block;
                width: 100%;
                max-width: 100%;
            }
            .desktop-sidebar,
            .desktop-content,
            .desktop-greeting,
            #cfo-dashboard,
            #network-status-banner,
            .tab-content {
                grid-column: auto;
                grid-row: auto;
                min-width: 0;
                width: 100%;
            }
            .desktop-sidebar {
                position: static;
            }
            /* Hide old horizontal tab nav on mobile */
            #dashboard-navigation {
                display: none !important;
            }
            #tab-expenses-content:not(.hidden),
            #tab-income-content:not(.hidden) {
                display: block;
            }
            #tab-income-content:not(.hidden) > #sales-main-view {
                display: block;
            }
        }

        /* Desktop layout */
        @media (min-width: 1024px) {
            body {
                min-height: 100vh;
                background: #000000;
            }
            #mobile-bottom-nav {
                display: none !important;
            }
            header > div {
                max-width: 1440px;
                padding-left: 28px;
                padding-right: 28px;
            }
            .desktop-dashboard-shell {
                display: grid;
                grid-template-columns: 260px minmax(0, 1fr);
                gap: 32px;
                align-items: start;
                width: calc(100% - 48px);
                max-width: 1440px;
                padding-left: 0;
                padding-right: 0;
                margin-top: 28px;
            }
            .desktop-sidebar {
                position: sticky;
                top: 80px;
                grid-column: 1;
                grid-row: 2 / span 5;
                padding: 14px;
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 22px;
                box-shadow: 0 8px 40px rgba(99,102,241,0.1);
            }
            .desktop-sidebar .tab-btn {
                width: 100%;
                justify-content: flex-start;
                min-width: 0;
                padding: 14px 16px;
                margin-bottom: 6px;
                border-radius: 14px;
                gap: 12px;
                font-size: 0.875rem;
                color: #9ca3af;
                background: transparent;
                border: none;
                transition: all 0.2s;
            }
            .desktop-sidebar .tab-btn:hover {
                background: #1e293b;
                color: #e2e8f0;
            }
            .desktop-sidebar .tab-btn.bg-indigo-600 {
                background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
                color: white !important;
                box-shadow: 0 4px 15px rgba(99,102,241,0.4);
            }
            .desktop-sidebar .tab-btn:last-child {
                margin-bottom: 0;
            }
            .desktop-content {
                grid-column: 2;
                min-width: 0;
            }
            #pwa-install-banner {
                grid-column: 1 / -1;
                grid-row: 1;
            }
            .desktop-greeting {
                grid-row: 2;
                margin-bottom: 22px;
                padding: 24px 28px;
                border-radius: 24px;
            }
            .desktop-greeting h2 {
                font-size: 1.25rem;
            }
            .desktop-greeting p {
                font-size: 0.8rem;
            }
            #cfo-dashboard {
                grid-row: 4;
                margin-bottom: 24px;
            }
            #cfo-dashboard #top-sales,
            #cfo-dashboard #top-expenses,
            #cfo-dashboard #top-profit {
                font-size: 1.35rem;
            }
            #cfo-dashboard p { font-size: 0.7rem; }
            #cfo-dashboard > div:first-child {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            #cfo-dashboard > div:last-child { margin-bottom: 0; }
            .desktop-content > .tab-content { min-width: 0; }
            #network-status-banner { grid-row: 3; }
            .desktop-content.tab-content { grid-row: 5; }
            #tab-expenses-content:not(.hidden),
            #tab-income-content:not(.hidden) {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                align-items: start;
                gap: 24px;
            }
            #tab-expenses-content:not(.hidden) > *,
            #tab-income-content:not(.hidden) > * { min-width: 0; }
            #tab-expenses-content:not(.hidden) > #search-report-results,
            #tab-expenses-content:not(.hidden) > #transaction-list { grid-column: 1 / -1; }
            #tab-income-content:not(.hidden) > #sales-main-view,
            #tab-income-content:not(.hidden) > #income-list { grid-column: 1 / -1; }
            #tab-income-content:not(.hidden) > #sales-main-view {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 24px;
            }
            #sales-main-view > div:first-child { grid-column: 1 / -1; }
            #sales-main-view > div:nth-child(2),
            #sales-main-view > div:nth-child(3) { min-width: 0; }
            #tab-analytics-content,
            #tab-profile-content { max-width: 100%; }
            .desktop-content input,
            .desktop-content select,
            .desktop-content .custom-select-button { min-height: 46px; }
            #digital-business-card { padding: 30px; }
            #profile-view-mode,
            #profile-edit-mode { max-width: 920px; }
            #tab-profile-content > .bg-white {
                padding: 28px;
            }
        }

        /* Glow animations */
        @keyframes glow-pulse {
            0%, 100% { box-shadow: 0 0 20px rgba(99,102,241,0.3); }
            50% { box-shadow: 0 0 35px rgba(99,102,241,0.6); }
        }
        .card-glow {
            animation: glow-pulse 3s ease-in-out infinite;
        }

        /* Scrollbar dark */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #374151; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #6366f1; }
    </style>"""
content = re.sub(r'<style>.*?</style>', style_replacement, content, flags=re.DOTALL)

# Update body tag
content = content.replace('<body class="bg-gray-50 text-gray-800 pb-16">', '<body class="bg-black text-gray-100" style="padding-bottom: env(safe-area-inset-bottom)">')

# Update header tag
content = content.replace('<header class="bg-gray-900 text-white p-3.5 sm:p-4 shadow-md sticky top-0 z-40">', '<header class="bg-black border-b border-indigo-900/30 text-white p-3.5 sm:p-4 shadow-2xl sticky top-0 z-40" style="backdrop-filter: blur(20px);">')

# Update greeting card
content = content.replace('bg-white rounded-2xl p-4 shadow-sm border border-gray-100', 'bg-gradient-to-r from-indigo-950 to-violet-950 rounded-2xl p-4 shadow-lg border border-indigo-800/50')

# CFO stat cards
content = content.replace('bg-emerald-50 border-emerald-200', 'bg-emerald-950/40 border-emerald-800/60')
content = content.replace('bg-rose-50 border-rose-200', 'bg-rose-950/40 border-rose-800/60')
content = content.replace('bg-indigo-50 border-indigo-200', 'bg-indigo-950/40 border-indigo-800/60')

# General replacements for colors
content = content.replace('bg-white', 'bg-gray-900')
content = content.replace('bg-gray-50', 'bg-gray-950')
content = content.replace('bg-gray-100', 'bg-gray-800')
content = content.replace('bg-slate-50', 'bg-slate-900')

content = content.replace('text-gray-800', 'text-gray-100')
content = content.replace('text-gray-700', 'text-gray-200')
content = content.replace('text-gray-600', 'text-gray-300')
content = content.replace('text-gray-500', 'text-gray-400')
content = content.replace('text-slate-900', 'text-slate-100')
content = content.replace('text-slate-700', 'text-slate-300')
content = content.replace('text-slate-500', 'text-slate-400')

content = content.replace('border-gray-100', 'border-gray-800')
content = content.replace('border-gray-200', 'border-gray-700')
content = content.replace('border-slate-200', 'border-slate-700')

# Outstanding alert
content = content.replace('bg-amber-50 border-amber-200', 'bg-amber-950/30 border-amber-800/50')
content = content.replace('text-amber-800', 'text-amber-300')
content = content.replace('text-amber-600', 'text-amber-400')
content = content.replace('text-amber-700', 'text-amber-300')

# Submit buttons
content = content.replace('bg-indigo-600 text-white font-bold py-3 rounded-lg hover:bg-indigo-700', 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-bold py-3 rounded-xl hover:from-indigo-500 hover:to-violet-500 shadow-lg shadow-indigo-900/50')
content = content.replace('bg-emerald-600 text-white font-bold py-3 rounded-lg hover:bg-emerald-700', 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white font-bold py-3 rounded-xl hover:from-emerald-500 hover:to-teal-500 shadow-lg shadow-emerald-900/50')

# Search report
content = content.replace('bg-indigo-950 border border-gray-800', 'bg-indigo-950/30 border border-indigo-800/50') # adjusted from earlier replacement
content = content.replace('bg-indigo-50 border-indigo-100', 'bg-indigo-950/50 border-indigo-800')

# Edit/Delete Buttons
content = content.replace('text-blue-600 bg-blue-50 px-2 py-1 rounded hover:bg-blue-100', 'text-blue-400 bg-blue-950/50 px-2 py-1 rounded hover:bg-blue-900/50 border border-blue-800/50')
content = content.replace('text-red-600 bg-red-50 px-2 py-1 rounded hover:bg-red-100', 'text-red-400 bg-red-950/50 px-2 py-1 rounded hover:bg-red-900/50 border border-red-800/50')

# Digital Business Card
# previous replacement might have made it bg-gray-900 rounded-3xl p-6 border border-slate-700/80 shadow-xl
content = content.replace('bg-gray-900 rounded-3xl p-6 border border-slate-700/80 shadow-xl', 'bg-gradient-to-br from-gray-900 to-indigo-950 rounded-3xl p-6 border border-indigo-800/40 shadow-2xl')

# Sales summary gradient card
content = content.replace('bg-gradient-to-br from-emerald-500 to-teal-700', 'bg-gradient-to-br from-emerald-600 via-teal-700 to-emerald-900')

# Profile action buttons
content = content.replace('bg-slate-800 hover:bg-slate-700 border border-slate-700', 'bg-gray-800 hover:bg-gray-700 border border-gray-600')
content = content.replace('bg-indigo-950 hover:bg-indigo-800 text-indigo-700 border border-indigo-700', 'bg-indigo-950 hover:bg-indigo-900 text-indigo-300 border border-indigo-800') # adjust based on earlier replace

# Expense cards
content = content.replace('expense-card flex justify-between items-center p-4 border-b border-gray-950 hover:bg-gray-950', 'expense-card flex justify-between items-center p-4 border-b border-gray-800 hover:bg-gray-800/50 transition')
content = content.replace('bg-indigo-800 text-indigo-600', 'bg-indigo-900 text-indigo-300') # adjusted from earlier replace

mobile_nav = """
<!-- Mobile Bottom Nav Bar -->
<nav id="mobile-bottom-nav" class="fixed bottom-0 left-0 right-0 z-50 lg:hidden flex items-center bg-black/95 backdrop-blur-xl border-t border-gray-800" style="padding-bottom: env(safe-area-inset-bottom);">
  <button data-mobile-tab="expenses" class="mobile-nav-btn flex-1 flex flex-col items-center py-2.5 gap-0.5 text-indigo-400">
    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
    <span class="text-[10px] font-bold">Expenses</span>
  </button>
  <button data-mobile-tab="income" class="mobile-nav-btn flex-1 flex flex-col items-center py-2.5 gap-0.5 text-gray-500">
    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/></svg>
    <span class="text-[10px] font-bold">Sales</span>
  </button>
  <button data-mobile-tab="analytics" class="mobile-nav-btn flex-1 flex flex-col items-center py-2.5 gap-0.5 text-gray-500">
    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>
    <span class="text-[10px] font-bold">Analytics</span>
  </button>
  <button data-mobile-tab="profile" class="mobile-nav-btn flex-1 flex flex-col items-center py-2.5 gap-0.5 text-gray-500">
    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/></svg>
    <span class="text-[10px] font-bold">Profile</span>
  </button>
</nav>

<script>
// Mobile bottom nav tab switching
(function() {
  const mobileBtns = document.querySelectorAll('#mobile-bottom-nav .mobile-nav-btn');
  mobileBtns.forEach(btn => {
    btn.addEventListener('click', function() {
      const tab = this.dataset.mobileTab;
      const desktopBtn = document.getElementById('btn-tab-' + tab);
      if (desktopBtn) desktopBtn.click();
      mobileBtns.forEach(b => {
        b.classList.remove('text-indigo-400');
        b.classList.add('text-gray-500');
      });
      this.classList.remove('text-gray-500');
      this.classList.add('text-indigo-400');
    });
  });
  ['expenses','income','analytics','profile'].forEach(tab => {
    const btn = document.getElementById('btn-tab-' + tab);
    if (btn) btn.addEventListener('click', function() {
      mobileBtns.forEach(b => {
        const t = b.dataset.mobileTab;
        if (t === tab) {
          b.classList.add('text-indigo-400');
          b.classList.remove('text-gray-500');
        } else {
          b.classList.remove('text-indigo-400');
          b.classList.add('text-gray-500');
        }
      });
    });
  });
})();
</script>
</body>
"""
content = content.replace('</body>', mobile_nav)

with open('C:\\Users\\HP\\Python_Project\\templates\\index.html', 'w', encoding='utf-8') as f:
    f.write(content)
