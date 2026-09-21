
        const CURRENT_USER_ID = 1;
        const DB_NAME = 'SoloBizDB_user_' + CURRENT_USER_ID;
        const DB_VERSION = 3;
        const STORE_NAME = 'expenses';
        const INCOME_STORE = 'income';
        const PROFILE_STORE = 'business_profile';

        // -------------------------------------------------------------
        // STEP 1 & 3: OFFLINE BOUNCER & FAIL-SAFE TICKET
        // -------------------------------------------------------------
        (function checkOfflineBouncer() {
            if (!navigator.onLine) {
                const isOfflineLoggedIn = localStorage.getItem('solobiz_logged_in');
                if (!isOfflineLoggedIn) {
                    window.location.href = '/login';
                }
            } else {
                localStorage.setItem('solobiz_logged_in', 'true');
            }
        })();

        // -------------------------------------------------------------
        // STEP 1: FAIL-SAFE LOCALSTORAGE STORE & FORWARD ENGINE
        // -------------------------------------------------------------
        function saveSaleOffline(saleData) {
            let unsyncedSales = JSON.parse(localStorage.getItem('unsynced_sales')) || [];
            unsyncedSales.push(saleData);
            localStorage.setItem('unsynced_sales', JSON.stringify(unsyncedSales));
            console.log("Sale saved locally in localStorage notebook!");
        }

        // -------------------------------------------------------------
        // STEP 2 & 5: AUTO-SYNC ENGINE FOR UNACCEPTED OFFLINE SALES
        // -------------------------------------------------------------
        async function syncOfflineSales() {
            let unsyncedSales = JSON.parse(localStorage.getItem('unsynced_sales')) || [];
            if (unsyncedSales.length === 0) return;

            console.log(`Attempting to sync ${unsyncedSales.length} offline sales...`);

            try {
                let response = await fetch('/api/sync-sales', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sales: unsyncedSales })
                });

                if (response.ok) {
                    localStorage.removeItem('unsynced_sales');
                    console.log("Offline sales successfully synced to database.");
                    if (typeof showToast === 'function') {
                        showToast("All offline sales have been successfully backed up to database!", "success");
                    }
                }
            } catch (error) {
                console.log("Still offline, will try syncing later.");
            }
        }

        // Fire auto-sync on load & when network connection is restored
        window.addEventListener('load', function() {
            if (navigator.onLine) {
                syncOfflineSales();
            }
        });
        window.addEventListener('online', syncOfflineSales);

        function handleLogout() {
            localStorage.clear();
            sessionStorage.clear();
            window.location.href = "/logout";
        }

        async function authenticatedFetch(url, options = {}) {
            return fetch(url, options);
        }

        // -------------------------------------------------------------
        // UNIFIED DOM METRICS UPDATER
        // Updates all 4 summary indicators on the page simultaneously
        // -------------------------------------------------------------
        function updateAllDashboardTotals(totalSales, totalExpenses) {
            const sales = parseFloat(totalSales) || 0;
            const expenses = parseFloat(totalExpenses) || 0;
            const netProfit = sales - expenses;

            const fmt = (val) => '₦' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

            // 1. Big central "Total Expenses" in Expenses tab
            const mainTotalEl = document.getElementById('main-dashboard-total');
            if (mainTotalEl) {
                mainTotalEl.dataset.total = expenses;
                mainTotalEl.innerText = fmt(expenses);
            }

            // 2. Top "Total Sales" summary card
            const topSalesEl = document.getElementById('top-sales') || document.getElementById('cfo-total-sales');
            if (topSalesEl) {
                topSalesEl.dataset.sales = sales;
                topSalesEl.innerText = fmt(sales);
            }

            // 3. Top "Total Expenses" summary card
            const topExpensesEl = document.getElementById('top-expenses') || document.getElementById('cfo-total-expenses');
            if (topExpensesEl) {
                topExpensesEl.innerText = fmt(expenses);
            }

            // 4. Top "Net Profit" summary card
            const topProfitEl = document.getElementById('top-profit') || document.getElementById('cfo-net-profit');
            if (topProfitEl) {
                topProfitEl.innerText = fmt(netProfit);
                // Only touch colour — preserve the stat-value layout class
                topProfitEl.style.color = netProfit < 0 ? '#b45309' : '#3730a3';
            }

            // Also flip the Net Profit card background when JS updates it live
            const npCard = topProfitEl ? topProfitEl.closest('[class*="rounded-2xl"]') : null;
            if (npCard) {
                if (netProfit < 0) {
                    npCard.classList.remove('bg-indigo-50', 'border-indigo-200');
                    npCard.classList.add('bg-amber-50', 'border-amber-200');
                } else {
                    npCard.classList.remove('bg-amber-50', 'border-amber-200');
                    npCard.classList.add('bg-indigo-50', 'border-indigo-200');
                }
            }
        }

        function openIndexedDB() {
            return new Promise((resolve, reject) => {
                const request = indexedDB.open(DB_NAME, DB_VERSION);

                request.onupgradeneeded = (event) => {
                    const db = event.target.result;
                    if (!db.objectStoreNames.contains(STORE_NAME)) {
                        const store = db.createObjectStore(STORE_NAME, { keyPath: 'local_id', autoIncrement: true });
                        store.createIndex('synced', 'synced', { unique: false });
                    }
                    if (!db.objectStoreNames.contains(INCOME_STORE)) {
                        const incomeStore = db.createObjectStore(INCOME_STORE, { keyPath: 'local_id', autoIncrement: true });
                        incomeStore.createIndex('synced', 'synced', { unique: false });
                    }
                    if (!db.objectStoreNames.contains(PROFILE_STORE)) {
                        db.createObjectStore(PROFILE_STORE, { keyPath: 'id' });
                    }
                };

                request.onsuccess = (event) => resolve(event.target.result);
                request.onerror = (event) => reject(event.target.error);
            });
        }

        const openDB = openIndexedDB;

        // -------------------------------------------------------------
        // STEP 2: BUSINESS PROFILE JS HANDLERS
        // -------------------------------------------------------------
        async function loadBusinessProfile() {
            const db = await openIndexedDB();

            if (navigator.onLine) {
                try {
                    const response = await authenticatedFetch('/api/business_profile');
                    const result = await response.json();
                    if (response.ok && result.status === 'success' && result.profile) {
                        const profileRecord = {
                            id: 'current',
                            server_id: result.profile.id || null,
                            company_name: result.profile.company_name || '',
                            business_phone: result.profile.business_phone || '',
                            business_address: result.profile.business_address || '',
                            whatsapp_number: result.profile.whatsapp_number || '',
                            instagram_handle: result.profile.instagram_handle || '',
                            store_policy: result.profile.store_policy || '',
                            brand_color: result.profile.brand_color || '#4F46E5',
                            logo_url: result.profile.logo_url || '',
                            store_slug: result.profile.store_slug || '',
                            synced: true,
                            updated_at: new Date().toISOString()
                        };

                        await new Promise((resolve, reject) => {
                            const tx = db.transaction(PROFILE_STORE, 'readwrite');
                            const req = tx.objectStore(PROFILE_STORE).put(profileRecord);
                            req.onsuccess = () => resolve(req.result);
                            req.onerror = (e) => reject(e.target.error);
                        });

                        window.SOLOBIZ_PROFILE = profileRecord;
                        return profileRecord;
                    }
                } catch (err) {
                    console.warn('Could not fetch business profile from API. Loading from IndexedDB cache.', err);
                }
            }

            const cached = await new Promise((resolve, reject) => {
                const tx = db.transaction(PROFILE_STORE, 'readonly');
                const req = tx.objectStore(PROFILE_STORE).get('current');
                req.onsuccess = () => resolve(req.result || null);
                req.onerror = (e) => reject(e.target.error);
            });
            if (cached) window.SOLOBIZ_PROFILE = cached;
            return cached;
        }

        async function saveBusinessProfile(formDataOrData) {
            const db = await openIndexedDB();
            let response, result;

            if (formDataOrData instanceof FormData) {
                response = await authenticatedFetch('/api/business_profile', {
                    method: 'POST',
                    body: formDataOrData
                });
            } else {
                response = await authenticatedFetch('/api/business_profile', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formDataOrData)
                });
            }

            result = await response.json();
            if (response.ok && result.status === 'success' && result.profile) {
                const p = result.profile;
                const profileRecord = {
                    id: 'current',
                    server_id: p.id || null,
                    company_name: p.company_name || '',
                    business_phone: p.business_phone || '',
                    business_address: p.business_address || '',
                    whatsapp_number: p.whatsapp_number || '',
                    instagram_handle: p.instagram_handle || '',
                    store_policy: p.store_policy || '',
                    brand_color: p.brand_color || '#4F46E5',
                    logo_url: p.logo_url || '',
                    store_slug: p.store_slug || '',
                    synced: true,
                    updated_at: new Date().toISOString()
                };

                await new Promise((resolve, reject) => {
                    const tx = db.transaction(PROFILE_STORE, 'readwrite');
                    const req = tx.objectStore(PROFILE_STORE).put(profileRecord);
                    req.onsuccess = () => resolve(req.result);
                    req.onerror = (e) => reject(e.target.error);
                });

                window.SOLOBIZ_PROFILE = profileRecord;
                return profileRecord;
            } else {
                throw new Error(result.message || 'Failed to save business profile');
            }
        }

        async function getBusinessProfileLocal() {
            return loadBusinessProfile();
        }

        async function saveBusinessProfileLocal(profileData) {
            return saveBusinessProfile(profileData);
        }

        // -------------------------------------------------------------
        // STEP 3: INCOME (SALES) OFFLINE LOGIC
        // -------------------------------------------------------------
        async function logSale(incomeData) {
            const db = await openIndexedDB();
            const customer_name = String(incomeData.customer_name || 'Walk-in Customer').trim();
            const receipt_id = incomeData.receipt_id || ('REC-' + Math.floor(Date.now() / 1000));

            let items = incomeData.items;
            if (!items || !Array.isArray(items) || items.length === 0) {
                items = [{
                    item_sold: String(incomeData.item_sold || '').trim(),
                    amount: parseFloat(incomeData.amount || 0)
                }];
            }

            const createdRecords = [];
            const isoDate = new Date().toISOString();

            const discount = parseFloat(incomeData.discount || 0);
            const deliveryFee = parseFloat(incomeData.deliveryFee || 0);
            const paymentMode = incomeData.paymentMode || 'Cash';
            const splitCash = parseFloat(incomeData.splitCash || 0);
            const splitTransfer = parseFloat(incomeData.splitTransfer || 0);

            for (const item of items) {
                const saleRecord = {
                    amount: parseFloat(item.amount),
                    item_sold: String(item.item_sold || '').trim(),
                    customer_name: customer_name,
                    receipt_id: receipt_id,
                    date: isoDate,
                    synced: false,
                    server_id: null,
                    discount: discount,
                    delivery_fee: deliveryFee,
                    payment_mode: paymentMode,
                    split_cash: splitCash,
                    split_transfer: splitTransfer
                };

                const local_id = await new Promise((resolve, reject) => {
                    const tx = db.transaction(INCOME_STORE, 'readwrite');
                    const req = tx.objectStore(INCOME_STORE).add(saleRecord);
                    req.onsuccess = () => resolve(req.result);
                    req.onerror = (e) => reject(e.target.error);
                });

                saleRecord.local_id = local_id;
                createdRecords.push(saleRecord);
            }

            if (navigator.onLine) {
                try {
                    const response = await authenticatedFetch('/api/income', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            customer_name: customer_name,
                            receipt_id: receipt_id,
                            items: items
                        })
                    });

                    const result = await response.json();
                    if (response.ok && result.status === 'success') {
                        const serverItems = Array.isArray(result.items) ? result.items : [result.income];
                        for (let i = 0; i < createdRecords.length; i++) {
                            const rec = createdRecords[i];
                            const serverMatch = serverItems[i] || serverItems[0];
                            rec.synced = true;
                            rec.server_id = serverMatch ? serverMatch.id : result.receipt_id;

                            const updateTx = db.transaction(INCOME_STORE, 'readwrite');
                            updateTx.objectStore(INCOME_STORE).put(rec);
                        }
                    } else {
                        // Backend error, queue in localStorage
                        for (const item of items) {
                            saveSaleOffline({
                                item: String(item.item_sold || '').trim(),
                                amount: parseFloat(item.amount || 0),
                                customer_name: customer_name,
                                receipt_id: receipt_id,
                                date: isoDate
                            });
                        }
                    }
                } catch (err) {
                    console.warn('Network error logging sale. Saved offline in localStorage & IndexedDB.', err);
                    for (const item of items) {
                        saveSaleOffline({
                            item: String(item.item_sold || '').trim(),
                            amount: parseFloat(item.amount || 0),
                            customer_name: customer_name,
                            receipt_id: receipt_id,
                            date: isoDate
                        });
                    }
                }
            } else {
                // Offline mode: queue in localStorage immediately
                for (const item of items) {
                    saveSaleOffline({
                        item: String(item.item_sold || '').trim(),
                        amount: parseFloat(item.amount || 0),
                        customer_name: customer_name,
                        receipt_id: receipt_id,
                        date: isoDate
                    });
                }
            }

            return createdRecords[0];
        }

        async function saveIncomeLocal(incomeData) {
            return logSale(incomeData);
        }

        async function getIncomeLocal() {
            const db = await openIndexedDB();
            return new Promise((resolve, reject) => {
                const tx = db.transaction(INCOME_STORE, 'readonly');
                const req = tx.objectStore(INCOME_STORE).getAll();
                req.onsuccess = () => resolve(req.result || []);
                req.onerror = (e) => reject(e.target.error);
            });
        }

        async function getExpensesLocal() {
            const db = await openIndexedDB();
            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, 'readonly');
                const req = tx.objectStore(STORE_NAME).getAll();
                req.onsuccess = () => resolve(req.result || []);
                req.onerror = (e) => reject(e.target.error);
            });
        }

        async function syncIncomeFromServer() {
            if (!navigator.onLine) return;
            try {
                const response = await authenticatedFetch('/api/income');
                if (!response.ok) return;
                const result = await response.json();
                if (result.status === 'success' && Array.isArray(result.income)) {
                    const db = await openIndexedDB();
                    const localIncome = await getIncomeLocal();
                    const existingServerIds = new Set(
                        localIncome.map(i => i.server_id).filter(Boolean)
                    );

                    let addedAny = false;
                    for (const item of result.income) {
                        if (!existingServerIds.has(item.id)) {
                            const record = {
                                amount: parseFloat(item.amount),
                                item_sold: item.item_sold,
                                customer_name: item.customer_name,
                                receipt_id: item.receipt_id || ('REC-' + item.id),
                                date: item.date,
                                synced: true,
                                server_id: item.id
                            };
                            await new Promise((resolve, reject) => {
                                const tx = db.transaction(INCOME_STORE, 'readwrite');
                                const req = tx.objectStore(INCOME_STORE).add(record);
                                req.onsuccess = () => resolve();
                                req.onerror = (e) => reject(e.target.error);
                            });
                            addedAny = true;
                        }
                    }
                    if (addedAny && typeof renderIncomeListUI === 'function') {
                        await renderIncomeListUI();
                    }
                }
            } catch (err) {
                console.warn('Could not sync income from server:', err);
            }
        }

        // -------------------------------------------------------------
        // BACKGROUND NETWORK RECONNECTION LISTENER
        // -------------------------------------------------------------
        async function syncAllPendingData() {
            if (!navigator.onLine) return;
            console.log('Network online. Executing syncAllPendingData across stores...');

            const db = await openIndexedDB();

            // 1. Sync pending Expenses
            try {
                const expTx = db.transaction(STORE_NAME, 'readonly');
                const getExpensesReq = expTx.objectStore(STORE_NAME).getAll();
                getExpensesReq.onsuccess = async () => {
                    const allExpenses = getExpensesReq.result || [];
                    const unsyncedExpenses = allExpenses.filter(item => !item.synced || item.pending_delete || item.pending_edit);

                    for (const item of unsyncedExpenses) {
                        if (item.pending_delete && item.id) {
                            try {
                                const res = await authenticatedFetch(`/api/expenses/${item.id}`, { method: 'DELETE' });
                                if (res.ok) {
                                    const delTx = db.transaction(STORE_NAME, 'readwrite');
                                    delTx.objectStore(STORE_NAME).delete(item.local_id);
                                }
                            } catch (e) {}
                        } else if (item.pending_edit && item.id) {
                            try {
                                const res = await authenticatedFetch(`/api/expenses/${item.id}`, {
                                    method: 'PUT',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ amount: item.amount, category: item.category, description: item.description })
                                });
                                if (res.ok) {
                                    item.pending_edit = false;
                                    item.synced = true;
                                    const editTx = db.transaction(STORE_NAME, 'readwrite');
                                    editTx.objectStore(STORE_NAME).put(item);
                                }
                            } catch (e) {}
                        } else if (!item.synced) {
                            try {
                                const res = await authenticatedFetch('/add', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ amount: item.amount, category: item.category, description: item.description })
                                });
                                const data = await res.json();
                                if (res.ok && data.status === 'success') {
                                    item.synced = true;
                                    item.id = data.expense.id;
                                    const addTx = db.transaction(STORE_NAME, 'readwrite');
                                    addTx.objectStore(STORE_NAME).put(item);
                                }
                            } catch (e) {}
                        }
                    }
                };
            } catch (err) {
                console.warn('Error syncing pending expenses:', err);
            }

            // 2. Sync pending Income / Sales
            try {
                const incTx = db.transaction(INCOME_STORE, 'readonly');
                const getIncomeReq = incTx.objectStore(INCOME_STORE).getAll();
                getIncomeReq.onsuccess = async () => {
                    const allIncome = getIncomeReq.result || [];
                    const unsyncedIncome = allIncome.filter(item => !item.synced);

                    for (const item of unsyncedIncome) {
                        try {
                            const res = await authenticatedFetch('/api/income', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    items: [{
                                        amount: item.amount,
                                        item_sold: item.item_sold,
                                        discount: item.discount,
                                        delivery_fee: item.delivery_fee,
                                        payment_mode: item.payment_mode,
                                        split_cash: item.split_cash,
                                        split_transfer: item.split_transfer
                                    }],
                                    customer_name: item.customer_name,
                                    receipt_id: item.receipt_id
                                })
                            });
                            const data = await res.json();
                            if (res.ok && data.status === 'success') {
                                item.synced = true;
                                item.server_id = data.income.id;
                                const updateIncTx = db.transaction(INCOME_STORE, 'readwrite');
                                updateIncTx.objectStore(INCOME_STORE).put(item);
                                console.log(`Background synced income #${item.local_id} (Server ID ${item.server_id})`);
                            }
                        } catch (e) {
                            console.warn(`Failed background sync for income #${item.local_id}:`, e);
                        }
                    }
                };
            } catch (err) {
                console.warn('Error syncing pending income:', err);
            }

            // Pull latest income from server to ensure device parity
            await syncIncomeFromServer();

            // 3. Sync pending Business Profile
            try {
                const profileTx = db.transaction(PROFILE_STORE, 'readonly');
                const getProfileReq = profileTx.objectStore(PROFILE_STORE).get('current');
                getProfileReq.onsuccess = async () => {
                    const profile = getProfileReq.result;
                    if (profile && !profile.synced) {
                        try {
                            const res = await authenticatedFetch('/api/business_profile', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    company_name: profile.company_name,
                                    business_phone: profile.business_phone,
                                    business_address: profile.business_address
                                })
                            });
                            const data = await res.json();
                            if (res.ok && data.status === 'success') {
                                profile.synced = true;
                                profile.server_id = data.profile.id;
                                const updateProfTx = db.transaction(PROFILE_STORE, 'readwrite');
                                updateProfTx.objectStore(PROFILE_STORE).put(profile);
                                console.log('Background synced business profile.');
                            }
                        } catch (e) {
                            console.warn('Failed background sync for business profile:', e);
                        }
                    }
                };
            } catch (err) {
                console.warn('Error syncing pending business profile:', err);
            }
        }

        // Attach online reconnection listener
        window.addEventListener('online', syncAllPendingData);

        async function saveExpenseToIndexedDB(expenseData) {
            const db = await openDB();
            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, 'readwrite');
                const store = tx.objectStore(STORE_NAME);
                const request = store.add(expenseData);

                request.onsuccess = (event) => resolve(event.target.result);
                request.onerror = (event) => reject(event.target.error);
            });
        }

        async function updateExpenseInIndexedDB(localId, updateData) {
            if (!localId) return null;
            const db = await openDB();
            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, 'readwrite');
                const store = tx.objectStore(STORE_NAME);
                const getReq = store.get(Number(localId));

                getReq.onsuccess = () => {
                    const record = getReq.result;
                    if (record) {
                        Object.assign(record, updateData);
                        const putReq = store.put(record);
                        putReq.onsuccess = () => resolve(record);
                        putReq.onerror = (e) => reject(e.target.error);
                    } else {
                        resolve(null);
                    }
                };
                getReq.onerror = (e) => reject(e.target.error);
            });
        }

        function recalculateTotalFromUI(deltaAmount = 0) {
            let salesVal = 0;
            const salesEl = document.getElementById('top-sales') || document.getElementById('cfo-total-sales');
            if (salesEl) {
                salesVal = parseFloat(salesEl.dataset.sales || salesEl.innerText.replace(/[^0-9.-]+/g, '')) || 0;
            }

            let expSum = 0;
            if (deltaAmount !== 0) {
                const expEl = document.getElementById('top-expenses') || document.getElementById('cfo-total-expenses');
                let current = parseFloat(expEl ? expEl.innerText.replace(/[^0-9.-]+/g, '') : 0) || 0;
                expSum = Math.max(0, current + deltaAmount);
            } else {
                document.querySelectorAll('.expense-amount-val').forEach(el => {
                    const val = parseFloat(el.textContent.replace(/[^0-9.-]+/g, '')) || 0;
                    expSum += val;
                });
            }

            updateAllDashboardTotals(salesVal, expSum);
        }

        // -------------------------------------------------------------
        // DELETE EXPENSE FUNCTION
        // -------------------------------------------------------------
        async function deleteExpense(local_id, server_id) {
            const isOnline = navigator.onLine;

            // 1. Instantly update/remove in IndexedDB
            if (local_id) {
                const db = await openDB();
                if (!server_id) {
                    // Local record never synced to server -> delete completely from IndexedDB
                    const tx = db.transaction(STORE_NAME, 'readwrite');
                    tx.objectStore(STORE_NAME).delete(Number(local_id));
                } else if (!isOnline) {
                    // Server item deleted while offline -> flag pending_delete: true
                    await updateExpenseInIndexedDB(local_id, { pending_delete: true });
                } else {
                    // Online -> remove from IndexedDB
                    const tx = db.transaction(STORE_NAME, 'readwrite');
                    tx.objectStore(STORE_NAME).delete(Number(local_id));
                }
            }

            // 2. Instantly update UI (remove DOM card)
            const selector = local_id ? `[data-local-id="${local_id}"]` : `[data-server-id="${server_id}"]`;
            const itemElement = document.querySelector(selector);
            if (itemElement) {
                itemElement.remove();
                recalculateTotalFromUI();
            }

            // Check if transaction list is empty
            const listContainer = document.getElementById('transaction-list');
            if (listContainer && listContainer.querySelectorAll('.expense-card').length === 0) {
                listContainer.innerHTML = `<p class="text-center text-gray-400 py-8 text-sm" id="no-expenses-msg">No expenses recorded yet.</p>`;
            }

            // 3. Send DELETE request to Python API if online & server_id exists
            if (isOnline && server_id) {
                try {
                    const response = await authenticatedFetch(`/api/expenses/${server_id}`, {
                        method: 'DELETE'
                    });
                    const result = await response.json();
                    if (response.ok && result.status === 'success') {
                        console.log(`Server expense #${server_id} deleted successfully.`);
                    } else {
                        console.warn(`Server deletion failed for #${server_id}:`, result.message);
                    }
                } catch (err) {
                    console.warn(`Network error deleting #${server_id}. Flagged for sync.`, err);
                    if (local_id) {
                        await updateExpenseInIndexedDB(local_id, { pending_delete: true });
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // EDIT EXPENSE FUNCTION
        // -------------------------------------------------------------
        async function editExpense(local_id, server_id, updatedData) {
            const isOnline = navigator.onLine;

            const amount = parseFloat(updatedData.amount);
            const category = String(updatedData.category).trim();
            const description = String(updatedData.description).trim();

            const updateObj = {
                amount: amount,
                category: category,
                description: description,
                pending_edit: !isOnline || !server_id,
                synced: isOnline && !!server_id
            };

            // 1. Update in IndexedDB instantly
            if (local_id) {
                await updateExpenseInIndexedDB(local_id, updateObj);
            }

            // 2. Instantly update UI DOM card
            const selector = local_id ? `[data-local-id="${local_id}"]` : `[data-server-id="${server_id}"]`;
            const itemElement = document.querySelector(selector);
            if (itemElement) {
                const categoryInitial = (category[0] || '').toUpperCase();
                const formattedAmount = amount.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                });

                const catElem = itemElement.querySelector('.expense-category-val');
                if (catElem) {
                    catElem.childNodes[0].textContent = category + ' ';
                }

                const descElem = itemElement.querySelector('.expense-desc-val');
                if (descElem) descElem.textContent = description;

                const iconElem = itemElement.querySelector('.category-icon-val');
                if (iconElem) iconElem.textContent = categoryInitial;

                const amtElem = itemElement.querySelector('.expense-amount-val');
                if (amtElem) amtElem.textContent = `₦${formattedAmount}`;

                let badge = itemElement.querySelector('.sync-badge');
                if (!updateObj.synced) {
                    if (!badge && catElem) {
                        catElem.insertAdjacentHTML('beforeend', `<span class="sync-badge text-[9px] font-semibold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded ml-1">Offline</span>`);
                    }
                } else if (badge) {
                    badge.remove();
                }
            }

            recalculateTotalFromUI();

            // 3. Send PUT request to Python API if online & server_id exists
            if (isOnline && server_id) {
                try {
                    const response = await authenticatedFetch(`/api/expenses/${server_id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ amount, category, description })
                    });

                    const result = await response.json();
                    if (response.ok && result.status === 'success') {
                        if (local_id) {
                            await updateExpenseInIndexedDB(local_id, {
                                pending_edit: false,
                                synced: true
                            });
                        }
                        console.log(`Server expense #${server_id} updated successfully via PUT.`);
                    } else {
                        console.warn(`Server update failed for #${server_id}:`, result.message);
                    }
                } catch (err) {
                    console.warn(`Network error updating #${server_id}. Flagged for sync.`, err);
                    if (local_id) {
                        await updateExpenseInIndexedDB(local_id, { pending_edit: true });
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // ONLINE SYNC HELPER
        // -------------------------------------------------------------
        async function syncExpenseToServer(expense) {
            try {
                const response = await authenticatedFetch('/add', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        amount: expense.amount,
                        category: expense.category,
                        description: expense.description
                    })
                });

                const result = await response.json();

                if (response.ok && result.status === 'success') {
                    const serverExpense = result.expense;
                    
                    // Mark as synced in IndexedDB
                    await updateExpenseInIndexedDB(expense.local_id, {
                        synced: true,
                        id: serverExpense.id
                    });

                    // Update UI element attributes & remove offline badge
                    const itemElement = document.querySelector(`[data-local-id="${expense.local_id}"]`);
                    if (itemElement) {
                        itemElement.setAttribute('data-server-id', serverExpense.id);
                        const syncBadge = itemElement.querySelector('.sync-badge');
                        if (syncBadge) syncBadge.remove();
                    }
                    console.log(`Expense #${expense.local_id} synced successfully with server ID ${serverExpense.id}.`);
                }
            } catch (err) {
                console.warn('Sync failed due to network error. Expense remains stored in IndexedDB.', err);
            }
        }

        // -------------------------------------------------------------
        // UI RENDERING HELPER
        // -------------------------------------------------------------
        function renderTransactionItem(expense) {
            const listContainer = document.getElementById('transaction-list');
            if (!listContainer) return;

            const emptyMsg = document.getElementById('no-expenses-msg');
            if (emptyMsg) emptyMsg.remove();

            const categoryInitial = (expense.category[0] || '').toUpperCase();
            const formattedAmount = parseFloat(expense.amount).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });

            const localIdAttr = expense.local_id ? `data-local-id="${expense.local_id}"` : '';
            const serverIdAttr = expense.server_id || expense.id ? `data-server-id="${expense.server_id || expense.id}"` : '';
            const offlineBadge = !expense.synced ? `<span class="sync-badge text-[9px] font-semibold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded ml-1">Offline</span>` : '';

            const itemHTML = `
            <div ${localIdAttr} ${serverIdAttr}
                 data-category="${expense.category}"
                 data-amount="${expense.amount}"
                 class="expense-card flex justify-between items-center p-4 border-b border-gray-50 hover:bg-gray-50 transition">
                <div class="flex items-center gap-3">
                    <div class="category-icon-val w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold text-lg">
                        ${categoryInitial}
                    </div>
                    <div>
                        <p class="expense-category-val font-bold text-gray-800 text-sm capitalize">
                            ${expense.category} ${offlineBadge}
                        </p>
                        <p class="expense-desc-val text-xs text-gray-500">${expense.description}</p>
                    </div>
                </div>
                <div class="text-right">
                    <p class="expense-amount-val font-bold text-gray-900 text-sm mb-1">₦${formattedAmount}</p>
                    <div class="flex gap-2 justify-end">
                        <button type="button" class="btn-edit text-[10px] uppercase tracking-wide font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded hover:bg-blue-100">Edit</button>
                        <button type="button" class="btn-delete text-[10px] uppercase tracking-wide font-bold text-red-600 bg-red-50 px-2 py-1 rounded hover:bg-red-100">Del</button>
                    </div>
                </div>
            </div>`;

            listContainer.insertAdjacentHTML('afterbegin', itemHTML);
        }

        // -------------------------------------------------------------
        // EVENT LISTENERS & MODAL HANDLERS
        // -------------------------------------------------------------
        document.addEventListener('DOMContentLoaded', () => {
            const addForm = document.getElementById('expense-form');

            // Add Expense Form Handler
            if (addForm) {
                addForm.addEventListener('submit', async (event) => {
                    event.preventDefault();

                    const amountInput = addForm.querySelector('[name="amount"]');
                    const categoryInput = addForm.querySelector('[name="category"]');
                    const descriptionInput = addForm.querySelector('[name="description"]');

                    const amount = parseFloat(amountInput.value.replace(/,/g, ''));
                    const category = categoryInput.value.trim();
                    const description = descriptionInput.value.trim();

                    if (!amount || !category || !description) return;

                    const localExpense = {
                        amount: amount,
                        category: category,
                        description: description,
                        date: new Date().toISOString(),
                        synced: false,
                        id: null
                    };

                    try {
                        const localId = await saveExpenseToIndexedDB(localExpense);
                        localExpense.local_id = localId;

                        renderTransactionItem(localExpense);
                        recalculateTotalFromUI();

                        addForm.reset();

                        if (navigator.onLine) {
                            syncExpenseToServer(localExpense);
                        }
                    } catch (err) {
                        console.error('Error saving expense locally:', err);
                        alert('Could not save expense locally.');
                    }
                });
            }

            // Delegate Edit and Delete Button Clicks on Transaction List
            const listContainer = document.getElementById('transaction-list');
            if (listContainer) {
                listContainer.addEventListener('click', (event) => {
                    const card = event.target.closest('.expense-card');
                    if (!card) return;

                    const localId = card.getAttribute('data-local-id') || null;
                    const serverId = card.getAttribute('data-server-id') || null;

                    if (event.target.classList.contains('btn-delete')) {
                        if (confirm('Are you sure you want to delete this expense?')) {
                            deleteExpense(localId, serverId);
                        }
                    } else if (event.target.classList.contains('btn-edit')) {
                        // Open edit modal with prefilled data
                        const catElem = card.querySelector('.expense-category-val');
                        const descElem = card.querySelector('.expense-desc-val');
                        const amtElem = card.querySelector('.expense-amount-val');

                        const currentCategory = catElem ? catElem.childNodes[0].textContent.trim() : '';
                        const currentDesc = descElem ? descElem.textContent.trim() : '';
                        const currentAmt = amtElem ? parseFloat(amtElem.textContent.replace(/[^0-9.-]+/g, '')) : 0;

                        document.getElementById('edit-local-id').value = localId || '';
                        document.getElementById('edit-server-id').value = serverId || '';
                        document.getElementById('edit-amount').value = currentAmt;
                        document.getElementById('edit-category').value = currentCategory;
                        document.getElementById('edit-description').value = currentDesc;

                        const modal = document.getElementById('edit-modal');
                        modal.classList.remove('hidden');
                        modal.classList.add('flex');
                    }
                });
            }

            // Edit Modal Close & Submit Handlers
            const closeModalBtn = document.getElementById('close-edit-modal');
            const editModal = document.getElementById('edit-modal');
            const editForm = document.getElementById('edit-expense-form');

            if (closeModalBtn) {
                closeModalBtn.addEventListener('click', () => {
                    editModal.classList.add('hidden');
                    editModal.classList.remove('flex');
                });
            }

            if (editForm) {
                editForm.addEventListener('submit', (e) => {
                    e.preventDefault();

                    const localId = document.getElementById('edit-local-id').value || null;
                    const serverId = document.getElementById('edit-server-id').value || null;
                    const amount = parseFloat(document.getElementById('edit-amount').value.replace(/,/g, ''));
                    const category = document.getElementById('edit-category').value;
                    const description = document.getElementById('edit-description').value;

                    editExpense(localId, serverId, { amount, category, description });

                    editModal.classList.add('hidden');
                    editModal.classList.remove('flex');
                });
            }

            // -------------------------------------------------------------
            // TAB SWITCHING LOGIC
            // -------------------------------------------------------------
            const btnExpenses = document.getElementById('btn-tab-expenses');
            const btnIncome = document.getElementById('btn-tab-income');
            const btnAnalytics = document.getElementById('btn-tab-analytics');
            const btnProfile = document.getElementById('btn-tab-profile');

            const contentExpenses = document.getElementById('tab-expenses-content');
            const contentIncome = document.getElementById('tab-income-content');
            const contentAnalytics = document.getElementById('tab-analytics-content');
            const contentProfile = document.getElementById('tab-profile-content');

            function switchTab(target) {
                [contentExpenses, contentIncome, contentAnalytics, contentProfile].forEach(el => el && el.classList.add('hidden'));
                [btnExpenses, btnIncome, btnAnalytics, btnProfile].forEach(btn => {
                    if (btn) btn.className = 'tab-btn flex-1 py-2.5 px-3 text-[11px] font-bold rounded-xl transition-all duration-200 text-gray-500 hover:text-gray-900 hover:bg-gray-50 flex items-center justify-center gap-1 sm:text-xs sm:gap-1.5';
                });

                if (target === 'expenses' && contentExpenses) {
                    contentExpenses.classList.remove('hidden');
                    if (btnExpenses) btnExpenses.className = 'tab-btn flex-1 py-2.5 px-3 text-[11px] font-bold rounded-xl transition-all duration-200 bg-indigo-600 text-white shadow-sm flex items-center justify-center gap-1 sm:text-xs sm:gap-1.5';
                } else if (target === 'income' && contentIncome) {
                    contentIncome.classList.remove('hidden');
                    if (btnIncome) btnIncome.className = 'tab-btn flex-1 py-2.5 px-3 text-[11px] font-bold rounded-xl transition-all duration-200 bg-emerald-600 text-white shadow-sm flex items-center justify-center gap-1 sm:text-xs sm:gap-1.5';
                    renderIncomeListUI();
                } else if (target === 'analytics' && contentAnalytics) {
                    contentAnalytics.classList.remove('hidden');
                    if (btnAnalytics) btnAnalytics.className = 'tab-btn flex-1 py-2.5 px-3 text-[11px] font-bold rounded-xl transition-all duration-200 bg-blue-600 text-white shadow-sm flex items-center justify-center gap-1 sm:text-xs sm:gap-1.5';
                    if (typeof renderAnalytics === 'function') renderAnalytics('daily');
                } else if (target === 'profile' && contentProfile) {
                    contentProfile.classList.remove('hidden');
                    if (btnProfile) btnProfile.className = 'tab-btn flex-1 py-2.5 px-3 text-[11px] font-bold rounded-xl transition-all duration-200 bg-indigo-600 text-white shadow-sm flex items-center justify-center gap-1 sm:text-xs sm:gap-1.5';
                    populateProfileFormUI();
                }
            }

            if (btnExpenses) btnExpenses.addEventListener('click', () => switchTab('expenses'));
            if (btnIncome) btnIncome.addEventListener('click', () => switchTab('income'));
            if (btnAnalytics) btnAnalytics.addEventListener('click', () => switchTab('analytics'));
            if (btnProfile) btnProfile.addEventListener('click', () => switchTab('profile'));

            // -------------------------------------------------------------
            // CFO DASHBOARD METRICS CALCULATION
            // Accepts optional { categoryFilter, amountMax } to show filtered totals.
            // When no filters are passed, shows grand totals.
            // -------------------------------------------------------------
            async function calculateDashboard({ categoryFilter = '', amountMax = null } = {}) {
                try {
                    const db = await openIndexedDB();
                    const fmt = (val) => '₦' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    const isFiltered = categoryFilter !== '' || amountMax !== null;

                    // --- Total Sales (always unfiltered — income has no category) ---
                    const incomeTx = db.transaction(INCOME_STORE, 'readonly');
                    const getIncomeReq = incomeTx.objectStore(INCOME_STORE).getAll();
                    const incomeItems = await new Promise(res => {
                        getIncomeReq.onsuccess = () => res(getIncomeReq.result || []);
                        getIncomeReq.onerror = () => res([]);
                    });
                    const totalSales = incomeItems
                        .filter(item => !item.pending_delete)
                        .reduce((sum, item) => sum + parseFloat(item.amount || 0), 0);

                    // --- Total Expenses (filtered by category and/or max amount) ---
                    const expTx = db.transaction(STORE_NAME, 'readonly');
                    const getExpReq = expTx.objectStore(STORE_NAME).getAll();
                    const allExpItems = await new Promise(res => {
                        getExpReq.onsuccess = () => res(getExpReq.result || []);
                        getExpReq.onerror = () => res([]);
                    });

                    const expItems = allExpItems.filter(item => {
                        if (item.pending_delete) return false;
                        if (categoryFilter && item.category !== categoryFilter) return false;
                        if (amountMax !== null && parseFloat(item.amount || 0) > amountMax) return false;
                        return true;
                    });

                    let totalExpenses = 0;
                    if (allExpItems.length > 0) {
                        totalExpenses = expItems.reduce((sum, item) => sum + parseFloat(item.amount || 0), 0);
                    } else {
                        const domTotalEl = document.getElementById('main-dashboard-total');
                        if (domTotalEl) totalExpenses = parseFloat(domTotalEl.dataset.total || '0') || 0;
                    }

                    // Update all dashboard elements simultaneously
                    updateAllDashboardTotals(totalSales, totalExpenses);

                    // --- Filtered result banner below filter controls ---
                    const banner = document.getElementById('filter-result-banner');
                    const bannerLabel = document.getElementById('filter-result-label');
                    const bannerTotal = document.getElementById('filter-result-total');
                    const clearBtn = document.getElementById('btn-clear-filters');

                    if (isFiltered && banner && bannerTotal) {
                        let labelParts = [];
                        if (categoryFilter) labelParts.push(categoryFilter);
                        if (amountMax !== null) labelParts.push(`≤ ₦${amountMax.toLocaleString()}`);
                        if (bannerLabel) bannerLabel.textContent = 'Filtered: ' + labelParts.join(' · ');
                        bannerTotal.textContent = fmt(totalExpenses);
                        banner.classList.remove('hidden');
                        if (clearBtn) clearBtn.classList.remove('hidden');
                    } else if (banner) {
                        banner.classList.add('hidden');
                        if (clearBtn) clearBtn.classList.add('hidden');
                    }
                } catch (err) {
                    console.warn('Error calculating CFO dashboard metrics:', err);
                }
            }

            function loadAndRenderExpenses() {
                calculateDashboard();
            }

            // -------------------------------------------------------------
            // STEP 3: PDF RECEIPT GENERATOR (jsPDF)
            // -------------------------------------------------------------
            window.generatePDFReceipt = async function(saleLocalId) {
                try {
                    const db = await openIndexedDB();

                    const profileRecord = await new Promise((resolve) => {
                        const tx = db.transaction(PROFILE_STORE, 'readonly');
                        const req = tx.objectStore(PROFILE_STORE).get('current');
                        req.onsuccess = () => resolve(req.result || null);
                        req.onerror = () => resolve(null);
                    });

                    const saleRecord = await new Promise((resolve) => {
                        const tx = db.transaction(INCOME_STORE, 'readonly');
                        const req = tx.objectStore(INCOME_STORE).get(Number(saleLocalId));
                        req.onsuccess = () => resolve(req.result || null);
                        req.onerror = () => resolve(null);
                    });

                    if (!saleRecord) { alert('Sale record not found.'); return; }

                    const allLocalIncome = await getIncomeLocal();
                    let receiptItems = [];
                    if (saleRecord.receipt_id) {
                        receiptItems = allLocalIncome.filter(i => i.receipt_id === saleRecord.receipt_id);
                    }
                    if (receiptItems.length === 0) receiptItems = [saleRecord];

                    // ── Data ──────────────────────────────────────────────────
                    const companyName     = (profileRecord?.company_name  || 'SoloBiz Vendor').toUpperCase();
                    const bizPhone        = profileRecord?.business_phone  || '';
                    const bizAddress      = profileRecord?.business_address || '';
                    const whatsappNumber  = profileRecord?.whatsapp_number || '';
                    const instagramHandle = profileRecord?.instagram_handle || '';
                    const storePolicy     = profileRecord?.store_policy || '';
                    const brandColorHex   = profileRecord?.brand_color || '#4F46E5';
                    const customerName    = saleRecord.customer_name || 'Valued Customer';
                    const receiptId       = saleRecord.receipt_id   || `REC-${String(saleLocalId).padStart(5,'0')}`;
                    
                    const dateObj         = saleRecord.date ? new Date(saleRecord.date) : new Date();
                    const dateStr         = dateObj.toLocaleDateString('en-NG', { day:'2-digit', month:'short', year:'numeric' });
                    const timeStr         = dateObj.toLocaleTimeString('en-NG', { hour:'2-digit', minute:'2-digit' });
                    
                    const grandTotal      = receiptItems.reduce((s,i) => s + parseFloat(i.amount||0), 0);
                    const discount        = parseFloat(saleRecord.discount || 0);
                    const deliveryFee     = parseFloat(saleRecord.delivery_fee || 0);
                    const finalTotal      = grandTotal - discount + deliveryFee;
                    const paymentMode     = saleRecord.payment_mode || 'Cash';
                    const splitCash       = parseFloat(saleRecord.split_cash || 0);
                    const splitTransfer   = parseFloat(saleRecord.split_transfer || 0);
                    const hasAdjustments  = discount > 0 || deliveryFee > 0;
                    const fmt             = (n) => 'NGN ' + n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});

                    function hexToRgb(hex) {
                        let c = (hex || '#4F46E5').replace('#', '');
                        if (c.length === 3) c = c.split('').map(x => x + x).join('');
                        const num = parseInt(c, 16) || 0x4F46E5;
                        return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
                    }
                    const [brandR, brandG, brandB] = hexToRgb(brandColorHex);

                    // ── Page size: 80mm wide, height auto ─────────────────────
                    const lineCount   = receiptItems.length;
                    const policyLines = storePolicy ? Math.ceil(storePolicy.length / 42) : 0;
                    const adjustmentHeight = (hasAdjustments ? 25 : 0) + (paymentMode === 'Split' ? 10 : 5);
                    const docHeight   = Math.max(180, 130 + (lineCount * 8) + (policyLines * 4.5) + adjustmentHeight);
                    const { jsPDF }   = window.jspdf;
                    const doc         = new jsPDF({ orientation:'portrait', unit:'mm', format:[80, docHeight] });

                    // ────────────────────────────────────────────────────────
                    // 1. HEADER BANNER (Brand Color & Dark Accent)
                    // ────────────────────────────────────────────────────────
                    doc.setFillColor(brandR, brandG, brandB);
                    doc.rect(0, 0, 80, 26, 'F');

                    doc.setFillColor(15, 23, 42); // Dark slate bottom bar accent
                    doc.rect(0, 26, 80, 2, 'F');

                    // Company Name
                    doc.setTextColor(255, 255, 255);
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(13);
                    doc.text(companyName, 40, 12, { align: 'center' });

                    // Official Receipt Badge
                    doc.setFillColor(255, 255, 255);
                    doc.roundedRect(18, 16.5, 44, 6, 1.5, 1.5, 'F');
                    doc.setTextColor(brandR, brandG, brandB);
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(7.5);
                    doc.text('OFFICIAL PAYMENT RECEIPT', 40, 20.7, { align: 'center' });

                    // ────────────────────────────────────────────────────────
                    // 2. VENDOR CONTACT INFO
                    // ────────────────────────────────────────────────────────
                    let y = 33;
                    doc.setFont('helvetica', 'normal');
                    doc.setFontSize(7.5);
                    doc.setTextColor(71, 85, 105);

                    let contactParts = [];
                    if (bizPhone) contactParts.push(`Tel: ${bizPhone}`);
                    if (whatsappNumber) contactParts.push(`WA: ${whatsappNumber}`);
                    if (contactParts.length > 0) {
                        doc.text(contactParts.join('  ·  '), 40, y, { align: 'center' });
                        y += 4.5;
                    }

                    if (instagramHandle) {
                        const handleStr = instagramHandle.startsWith('@') ? instagramHandle : '@' + instagramHandle;
                        doc.text(`Instagram: ${handleStr}`, 40, y, { align: 'center' });
                        y += 4.5;
                    }
                    if (bizAddress) {
                        doc.text(bizAddress, 40, y, { align: 'center' });
                        y += 4.5;
                    }
                    y += 1;

                    // Divider
                    doc.setDrawColor(226, 232, 240);
                    doc.setLineWidth(0.3);
                    doc.line(5, y, 75, y);
                    y += 5;

                    // ────────────────────────────────────────────────────────
                    // 3. INVOICE META & CUSTOMER DETAILS BOX
                    // ────────────────────────────────────────────────────────
                    doc.setFillColor(248, 250, 252);
                    doc.roundedRect(4, y, 72, 22, 2, 2, 'F');
                    doc.setDrawColor(226, 232, 240);
                    doc.roundedRect(4, y, 72, 22, 2, 2, 'S');

                    const metaLeft  = 7;
                    const metaRight = 73;

                    // Receipt No
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(7.5);
                    doc.setTextColor(100, 116, 139);
                    doc.text('Receipt No:', metaLeft, y + 5.5);
                    doc.setFont('helvetica', 'bold');
                    doc.setTextColor(15, 23, 42);
                    doc.text(receiptId, metaRight, y + 5.5, { align: 'right' });

                    // Date & Time
                    doc.setFont('helvetica', 'bold');
                    doc.setTextColor(100, 116, 139);
                    doc.text('Date & Time:', metaLeft, y + 11.5);
                    doc.setFont('helvetica', 'normal');
                    doc.setTextColor(15, 23, 42);
                    doc.text(`${dateStr}  ${timeStr}`, metaRight, y + 11.5, { align: 'right' });

                    // Customer Name & Paid Badge
                    doc.setFont('helvetica', 'bold');
                    doc.setTextColor(100, 116, 139);
                    doc.text('Customer:', metaLeft, y + 17.5);
                    doc.setFont('helvetica', 'bold');
                    doc.setTextColor(16, 185, 129); // Green paid status
                    doc.text(`${customerName}  [ PAID ]`, metaRight, y + 17.5, { align: 'right' });

                    y += 27;

                    // ────────────────────────────────────────────────────────
                    // 4. ITEMIZED PURCHASE TABLE
                    // ────────────────────────────────────────────────────────
                    // Table Header
                    doc.setFillColor(15, 23, 42);
                    doc.rect(4, y, 72, 7, 'F');
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(7.5);
                    doc.setTextColor(255, 255, 255);
                    doc.text('ITEM / DESCRIPTION', metaLeft, y + 4.5);
                    doc.text('AMOUNT (NGN)', metaRight, y + 4.5, { align: 'right' });
                    y += 7;

                    // Table Rows
                    doc.setFont('helvetica', 'normal');
                    doc.setFontSize(8);

                    receiptItems.forEach((item, idx) => {
                        if (idx % 2 === 0) {
                            doc.setFillColor(248, 250, 252);
                            doc.rect(4, y, 72, 7.5, 'F');
                        }
                        doc.setTextColor(30, 41, 59);
                        const title = item.item_sold || 'Goods / Services';
                        const amt   = parseFloat(item.amount || 0).toLocaleString('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });
                        const splitTitle = doc.splitTextToSize(title, 38)[0];
                        doc.text(splitTitle, metaLeft, y + 5);
                        doc.setFont('helvetica', 'bold');
                        doc.text(amt, metaRight, y + 5, { align: 'right' });
                        doc.setFont('helvetica', 'normal');
                        y += 7.5;
                    });

                    // Bottom table border line
                    doc.setDrawColor(203, 213, 225);
                    doc.line(4, y, 76, y);
                    y += 4;

                    // ────────────────────────────────────────────────────────
                    // 5. ADJUSTMENTS & TOTAL PAID
                    // ────────────────────────────────────────────────────────
                    if (hasAdjustments) {
                        doc.setFont('helvetica', 'normal');
                        doc.setFontSize(7.5);
                        doc.setTextColor(100, 116, 139);
                        doc.text('Subtotal:', metaLeft, y + 4);
                        doc.setFont('helvetica', 'bold');
                        doc.text(fmt(grandTotal), metaRight, y + 4, { align: 'right' });
                        y += 6;

                        if (discount > 0) {
                            doc.setFont('helvetica', 'normal');
                            doc.setTextColor(220, 38, 38);
                            doc.text('Discount:', metaLeft, y + 4);
                            doc.setFont('helvetica', 'bold');
                            doc.text('- ' + fmt(discount), metaRight, y + 4, { align: 'right' });
                            y += 6;
                        }

                        if (deliveryFee > 0) {
                            doc.setFont('helvetica', 'normal');
                            doc.setTextColor(37, 99, 235);
                            doc.text('Delivery / Waybill:', metaLeft, y + 4);
                            doc.setFont('helvetica', 'bold');
                            doc.text('+ ' + fmt(deliveryFee), metaRight, y + 4, { align: 'right' });
                            y += 6;
                        }
                        y += 2;
                    }

                    doc.setFillColor(15, 23, 42);
                    doc.roundedRect(4, y, 72, 13, 2, 2, 'F');
                    
                    // Brand color side strip
                    doc.setFillColor(brandR, brandG, brandB);
                    doc.roundedRect(4, y, 3.5, 13, 1, 1, 'F');

                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(8.5);
                    doc.setTextColor(226, 232, 240);
                    doc.text('TOTAL AMOUNT PAID', 11, y + 8.5);
                    doc.setFontSize(10.5);
                    doc.setTextColor(255, 255, 255);
                    doc.text(fmt(finalTotal), metaRight, y + 8.5, { align: 'right' });

                    y += 16;

                    // Payment mode badge
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(7);
                    doc.setTextColor(100, 116, 139);
                    if (paymentMode === 'Split') {
                        doc.text(`Paid: \u20a6${splitCash.toLocaleString()} Cash + \u20a6${splitTransfer.toLocaleString()} Transfer`, 40, y, { align: 'center' });
                    } else {
                        doc.text(`Payment Mode: ${paymentMode}`, 40, y, { align: 'center' });
                    }
                    y += 5;

                    // ────────────────────────────────────────────────────────
                    // 6. STORE POLICY & FOOTER
                    // ────────────────────────────────────────────────────────
                    if (storePolicy) {
                        doc.setFillColor(241, 245, 249);
                        doc.setDrawColor(226, 232, 240);
                        
                        const policyLinesArr = doc.splitTextToSize(`Policy: ${storePolicy}`, 68);
                        const boxH = (policyLinesArr.length * 4) + 4;

                        doc.roundedRect(4, y, 72, boxH, 1.5, 1.5, 'F');
                        doc.roundedRect(4, y, 72, boxH, 1.5, 1.5, 'S');

                        doc.setFont('helvetica', 'normal');
                        doc.setFontSize(6.5);
                        doc.setTextColor(71, 85, 105);
                        doc.text(policyLinesArr, 40, y + 4, { align: 'center' });

                        y += boxH + 6;
                    }

                    // Thank you note
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(8.5);
                    doc.setTextColor(15, 23, 42);
                    doc.text('Thank you for your business!', 40, y, { align: 'center' });
                    y += 4.5;

                    doc.setFont('helvetica', 'italic');
                    doc.setFontSize(7);
                    doc.setTextColor(100, 116, 139);
                    doc.text('Payment verified and received in full.', 40, y, { align: 'center' });
                    y += 6;

                    // Bottom Watermark Bar
                    doc.setFillColor(241, 245, 249);
                    doc.rect(0, y, 80, 10, 'F');
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(6.5);
                    doc.setTextColor(brandR, brandG, brandB);
                    doc.text('SoloBiz Pocket CFO', 40, y + 4, { align: 'center' });
                    doc.setFont('helvetica', 'normal');
                    doc.setTextColor(148, 163, 184);
                    doc.text('Verified Financial Document · solobiz.dev', 40, y + 7.5, { align: 'center' });

                    // Save PDF & offer native sharing
                    const safeName = customerName.replace(/[^a-zA-Z0-9]/g, '_');
                    const pdfFileName = `Receipt_${safeName}_${receiptId}.pdf`;

                    // Try Web Share API first (native mobile sharing)
                    if (navigator.share && navigator.canShare) {
                        try {
                            const pdfBlob = doc.output('blob');
                            const pdfFile = new File([pdfBlob], pdfFileName, { type: 'application/pdf' });
                            if (navigator.canShare({ files: [pdfFile] })) {
                                await navigator.share({
                                    title: `Receipt - ${customerName}`,
                                    text: `Receipt ${receiptId} from ${companyName} - ${fmt(finalTotal)}`,
                                    files: [pdfFile]
                                });
                                return; // Shared successfully
                            }
                        } catch (shareErr) {
                            if (shareErr.name !== 'AbortError') {
                                console.warn('Web Share failed, falling back to download:', shareErr);
                            } else {
                                return; // User cancelled share
                            }
                        }
                    }
                    // Fallback: direct download
                    doc.save(pdfFileName);

                } catch (err) {
                    console.error('Error generating PDF receipt:', err);
                    alert('Could not generate PDF. Make sure you have internet so the PDF library can load.');
                }
            };

            window.generateWhatsAppReceipt = window.generatePDFReceipt;

            // -------------------------------------------------------------
            // SALES / INCOME UI HANDLERS
            // -------------------------------------------------------------
            function renderIncomeItemHTML(income) {
                const offlineBadge = !income.synced ? `<span class="text-[9px] font-semibold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded ml-1">Offline</span>` : '';
                const formattedAmount = parseFloat(income.amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const receiptTag = income.receipt_id ? `<span class="text-[10px] text-gray-400 font-mono ml-1.5">#${income.receipt_id}</span>` : '';

                return `
                <div data-income-local-id="${income.local_id || ''}" class="flex justify-between items-center p-4 border-b border-gray-50 hover:bg-gray-50 transition">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-lg">💰</div>
                        <div>
                            <p class="font-bold text-gray-800 text-sm capitalize flex items-center">
                                ${income.item_sold} ${offlineBadge}
                            </p>
                            <p class="text-xs text-gray-500">Customer: ${income.customer_name || 'Walk-in'} ${receiptTag}</p>
                        </div>
                    </div>
                    <div class="text-right">
                        <p class="font-bold text-emerald-600 text-sm mb-1">₦${formattedAmount}</p>
                        <button type="button" onclick="generatePDFReceipt(${income.local_id})" class="inline-flex items-center gap-1 text-[10px] uppercase font-bold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1 rounded transition border border-emerald-200 shadow-sm">
                            <span>📄</span> Download Receipt
                        </button>
                    </div>
                </div>`;
            }

            async function renderIncomeListUI() {
                const listContainer = document.getElementById('income-list');
                const totalIncomeEl = document.getElementById('total-income-amount');
                if (!listContainer) return;

                const incomeItems = await getIncomeLocal();
                let totalIncome = 0;

                if (incomeItems.length === 0) {
                    listContainer.innerHTML = `<p class="text-center text-gray-400 py-8 text-sm" id="no-income-msg">No sales recorded yet.</p>`;
                } else {
                    listContainer.innerHTML = incomeItems.map(item => {
                        totalIncome += parseFloat(item.amount || 0);
                        return renderIncomeItemHTML(item);
                    }).reverse().join('');
                }

                if (totalIncomeEl) {
                    totalIncomeEl.textContent = '₦' + totalIncome.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }

                calculateDashboard();
            }

            // Multi-item row adder logic
            const btnAddItemRow = document.getElementById('btn-add-sale-item-row');
            const saleItemsContainer = document.getElementById('sale-items-container');

            function updateRemoveButtonsVisibility() {
                if (!saleItemsContainer) return;
                const rows = saleItemsContainer.querySelectorAll('.sale-item-row');
                rows.forEach(row => {
                    const removeBtn = row.querySelector('.btn-remove-item-row');
                    if (removeBtn) {
                        removeBtn.classList.toggle('hidden', rows.length <= 1);
                    }
                });
            }

            if (btnAddItemRow && saleItemsContainer) {
                btnAddItemRow.addEventListener('click', () => {
                    const rowHTML = `
                    <div class="sale-item-row grid grid-cols-12 gap-2 items-center bg-gray-50/70 p-2.5 rounded-xl border border-gray-100">
                        <div class="col-span-7">
                            <input type="text" name="item_sold[]" class="income-item-sold w-full border border-gray-200 rounded-lg p-2.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition" placeholder="Item / Service (e.g. Eden Cap)" required>
                        </div>
                        <div class="col-span-4">
                            <div class="relative">
                                <span class="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 font-bold text-sm">₦</span>
                                <input type="text" inputmode="numeric" name="amount[]" class="currency-input income-amount w-full border border-gray-200 rounded-lg py-2.5 pr-2.5 pl-7 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition" placeholder="Amount" required>
                            </div>
                        </div>
                        <div class="col-span-1 text-center">
                            <button type="button" class="btn-remove-item-row text-red-500 hover:text-red-700 text-sm font-bold p-1">✕</button>
                        </div>
                    </div>`;
                    saleItemsContainer.insertAdjacentHTML('beforeend', rowHTML);
                    updateRemoveButtonsVisibility();
                });

                saleItemsContainer.addEventListener('click', (e) => {
                    if (e.target && e.target.classList.contains('btn-remove-item-row')) {
                        const row = e.target.closest('.sale-item-row');
                        if (row && saleItemsContainer.querySelectorAll('.sale-item-row').length > 1) {
                            row.remove();
                            updateRemoveButtonsVisibility();
                        }
                    }
                });
            }

            const addIncomeForm = document.getElementById('add-income-form');
            if (addIncomeForm) {
                addIncomeForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const customer_name = document.getElementById('income-customer-name').value.trim() || 'Walk-in Customer';
                    const itemRows = saleItemsContainer ? saleItemsContainer.querySelectorAll('.sale-item-row') : [];

                    const items = [];
                    itemRows.forEach(row => {
                        const item_sold = row.querySelector('.income-item-sold')?.value.trim();
                        const amount = parseFloat((row.querySelector('.income-amount')?.value || '').replace(/,/g, ''));
                        if (item_sold && !isNaN(amount) && amount > 0) {
                            items.push({ item_sold, amount });
                        }
                    });

                    if (items.length === 0) return;

                    // Receipt adjustments
                    const discount = parseFloat((document.getElementById('sale-discount')?.value || '0').replace(/,/g, '')) || 0;
                    const deliveryFee = parseFloat((document.getElementById('sale-delivery-fee')?.value || '0').replace(/,/g, '')) || 0;
                    const paymentMode = document.getElementById('sale-payment-mode')?.value || 'Cash';
                    let splitCash = 0, splitTransfer = 0;
                    if (paymentMode === 'Split') {
                        splitCash = parseFloat((document.getElementById('sale-split-cash')?.value || '0').replace(/,/g, '')) || 0;
                        splitTransfer = parseFloat((document.getElementById('sale-split-transfer')?.value || '0').replace(/,/g, '')) || 0;
                    }

                    await logSale({ customer_name, items, discount, deliveryFee, paymentMode, splitCash, splitTransfer });

                    addIncomeForm.reset();
                    // Reset to single item row
                    if (saleItemsContainer) {
                        saleItemsContainer.innerHTML = `
                        <div class="sale-item-row grid grid-cols-12 gap-2 items-center bg-gray-50/70 p-2.5 rounded-xl border border-gray-100">
                            <div class="col-span-7">
                                <input type="text" name="item_sold[]" class="income-item-sold w-full border border-gray-200 rounded-lg p-2.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition" placeholder="Item / Service (e.g. DLNZ Hoodie)" required>
                            </div>
                            <div class="col-span-4">
                                <div class="relative">
                                    <span class="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 font-bold text-sm">₦</span>
                                    <input type="text" inputmode="numeric" name="amount[]" class="currency-input income-amount w-full border border-gray-200 rounded-lg py-2.5 pr-2.5 pl-7 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition" placeholder="Amount" required>
                                </div>
                            </div>
                            <div class="col-span-1 text-center">
                                <button type="button" class="btn-remove-item-row hidden text-red-500 hover:text-red-700 text-sm font-bold p-1">✕</button>
                            </div>
                        </div>`;
                    }
                    renderIncomeListUI();
                    calculateDashboard();
                });
            }

            // =========================================================
            // QUICK-TAP INVENTORY PRESETS
            // =========================================================
            let inventoryPresets = [];
            const presetsGrid = document.getElementById('presets-grid');
            const noPresetsMsg = document.getElementById('no-presets-msg');
            const managePanel = document.getElementById('manage-presets-panel');
            const manageList = document.getElementById('presets-manage-list');

            // Split Payment Mode toggle
            document.getElementById('sale-payment-mode')?.addEventListener('change', function() {
                const splitFields = document.getElementById('split-payment-fields');
                if (splitFields) {
                    splitFields.classList.toggle('hidden', this.value !== 'Split');
                    if (this.value !== 'Split') splitFields.classList.add('hidden');
                    else splitFields.classList.remove('hidden');
                }
            });

            // Toggle manage panel
            document.getElementById('btn-manage-presets')?.addEventListener('click', () => {
                managePanel.classList.toggle('hidden');
            });

            // Render the quick-tap grid buttons
            function renderPresetsGrid() {
                if (!presetsGrid) return;
                const buttons = inventoryPresets.map(p => {
                    const isLow = p.stock > 0 && p.stock <= 3;
                    const isOut = p.stock === 0 && inventoryPresets.some(x => x.stock > 0); // only flag if stock tracking is used
                    const stockBadge = p.stock > 0
                        ? `<span class="text-[9px] ${isLow ? 'text-amber-600 font-bold' : 'text-gray-400'}">${isLow ? '⚠ ' : ''}${p.stock} left</span>`
                        : '';
                    const outClass = isOut ? 'opacity-40 pointer-events-none' : '';
                    return `<button type="button" data-preset-id="${p.id}" data-name="${p.item_name}" data-price="${p.price}"
                        class="preset-tap-btn ${outClass} bg-gradient-to-br from-gray-50 to-white border border-gray-200 hover:border-emerald-400 hover:shadow-md rounded-xl p-2.5 text-center transition-all active:scale-95 cursor-pointer">
                        <p class="text-xs font-bold text-gray-800 truncate">${p.item_name}</p>
                        <p class="text-[11px] font-bold text-emerald-600">₦${p.price.toLocaleString()}</p>
                        ${stockBadge}
                    </button>`;
                }).join('');

                if (inventoryPresets.length === 0) {
                    presetsGrid.innerHTML = '<p id="no-presets-msg" class="col-span-3 text-center text-gray-400 text-xs py-4">No presets yet. Tap ⚙ Manage to add your top items.</p>';
                } else {
                    presetsGrid.innerHTML = buttons;
                }
            }

            // Render manage list (edit/delete rows)
            function renderManageList() {
                if (!manageList) return;
                manageList.innerHTML = inventoryPresets.map(p => `
                    <div class="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 text-xs" data-manage-id="${p.id}">
                        <span class="flex-1 font-semibold text-gray-800 truncate">${p.item_name}</span>
                        <span class="text-emerald-600 font-bold whitespace-nowrap">₦${p.price.toLocaleString()}</span>
                        <span class="text-gray-400 whitespace-nowrap w-12 text-center">${p.stock} pcs</span>
                        <button type="button" class="btn-delete-preset text-red-400 hover:text-red-600 font-bold transition" data-id="${p.id}">✕</button>
                    </div>
                `).join('');
            }

            // Load presets from server
            async function loadPresets() {
                try {
                    const res = await authenticatedFetch('/api/inventory-presets');
                    const data = await res.json();
                    if (data.status === 'success') {
                        inventoryPresets = data.presets;
                        renderPresetsGrid();
                        renderManageList();
                    }
                } catch (e) { console.warn('Presets load failed:', e); }
            }

            // Add preset form
            document.getElementById('add-preset-form')?.addEventListener('submit', async (e) => {
                e.preventDefault();
                const item_name = document.getElementById('preset-item-name').value.trim();
                const price = parseFloat((document.getElementById('preset-price').value || '').replace(/,/g, ''));
                const stock = parseInt(document.getElementById('preset-stock').value || '0', 10);
                if (!item_name || isNaN(price) || price <= 0) return;

                try {
                    const res = await authenticatedFetch('/api/inventory-presets', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ item_name, price, stock })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        inventoryPresets.push(data.preset);
                        renderPresetsGrid();
                        renderManageList();
                        e.target.reset();
                    } else {
                        alert(data.message || 'Failed to add preset');
                    }
                } catch (err) { alert('Network error adding preset.'); }
            });

            // Delete preset
            manageList?.addEventListener('click', async (e) => {
                const deleteBtn = e.target.closest('.btn-delete-preset');
                if (!deleteBtn) return;
                const id = parseInt(deleteBtn.dataset.id, 10);
                try {
                    await authenticatedFetch(`/api/inventory-presets/${id}`, { method: 'DELETE' });
                    inventoryPresets = inventoryPresets.filter(p => p.id !== id);
                    renderPresetsGrid();
                    renderManageList();
                } catch (err) { console.error('Delete preset error:', err); }
            });

            // Quick-Tap: add item to sale form
            presetsGrid?.addEventListener('click', async (e) => {
                const btn = e.target.closest('.preset-tap-btn');
                if (!btn) return;
                const presetId = parseInt(btn.dataset.presetId, 10);
                const name = btn.dataset.name;
                const price = btn.dataset.price;

                // Fill the first empty row OR add a new row
                const container = document.getElementById('sale-items-container');
                if (!container) return;

                const rows = container.querySelectorAll('.sale-item-row');
                let filled = false;
                for (const row of rows) {
                    const nameInput = row.querySelector('.income-item-sold');
                    const amountInput = row.querySelector('.income-amount');
                    if (nameInput && !nameInput.value.trim()) {
                        nameInput.value = name;
                        amountInput.value = parseInt(price, 10).toLocaleString('en-US');
                        filled = true;
                        break;
                    }
                }

                if (!filled) {
                    // Click the "Add Item" button to create a new row, then fill it
                    document.getElementById('btn-add-sale-item-row')?.click();
                    await new Promise(r => setTimeout(r, 50));
                    const newRows = container.querySelectorAll('.sale-item-row');
                    const lastRow = newRows[newRows.length - 1];
                    if (lastRow) {
                        const nameInput = lastRow.querySelector('.income-item-sold');
                        const amountInput = lastRow.querySelector('.income-amount');
                        if (nameInput) nameInput.value = name;
                        if (amountInput) amountInput.value = parseInt(price, 10).toLocaleString('en-US');
                    }
                }

                // Decrement stock in background
                const preset = inventoryPresets.find(p => p.id === presetId);
                if (preset && preset.stock > 0) {
                    try {
                        const res = await authenticatedFetch(`/api/inventory-presets/${presetId}/decrement`, { method: 'POST' });
                        const data = await res.json();
                        preset.stock = data.stock;
                        renderPresetsGrid();
                        renderManageList();
                    } catch (err) { console.warn('Stock decrement failed:', err); }
                }
            });

            // Load presets on init
            loadPresets();

            // =========================================================
            // SALES ANALYTICS ENGINE
            // =========================================================
            const salesMainView = document.getElementById('sales-main-view');
            const analyticsView = document.getElementById('analytics-view');
            
            document.getElementById('btn-show-analytics')?.addEventListener('click', () => {
                if(salesMainView && analyticsView) {
                    salesMainView.classList.add('hidden');
                    analyticsView.classList.remove('hidden');
                    renderAnalytics('daily'); // default
                }
            });

            // Handle the top header "Overview" button
            document.getElementById('btn-global-overview')?.addEventListener('click', () => {
                // Switch to the Analytics Tab directly
                if (typeof switchTab === 'function') switchTab('analytics');
                
                // Scroll to top to see it clearly
                window.scrollTo({ top: 0, behavior: 'smooth' });
            });

            document.getElementById('btn-hide-analytics')?.addEventListener('click', () => {
                if(salesMainView && analyticsView) {
                    analyticsView.classList.add('hidden');
                    salesMainView.classList.remove('hidden');
                }
            });

            const analyticsTabs = document.querySelectorAll('.analytics-tab-btn');
            analyticsTabs.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const period = e.target.dataset.period;
                    // Update active tab styles
                    analyticsTabs.forEach(t => {
                        t.classList.remove('bg-white', 'shadow-sm', 'text-gray-900');
                        t.classList.add('text-gray-500');
                    });
                    e.target.classList.remove('text-gray-500');
                    e.target.classList.add('bg-white', 'shadow-sm', 'text-gray-900');
                    renderAnalytics(period);
                });
            });

            async function renderAnalytics(period) {
                const incomeItems = await getIncomeLocal();
                const expenseItems = await getExpensesLocal();
                
                // Helper to format date keys
                const getPeriodKey = (dateStr) => {
                    const d = new Date(dateStr);
                    if (period === 'daily') return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
                    if (period === 'weekly') {
                        const first = d.getDate() - d.getDay();
                        const weekStart = new Date(d.setDate(first));
                        return "Week of " + weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    }
                    if (period === 'monthly') return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
                    if (period === 'yearly') return d.getFullYear().toString();
                    return 'Unknown';
                };

                // Group data for the expandable list
                const groups = {};
                
                // Global Totals
                let totalRevenue = 0;
                let totalCOGS = 0;
                let totalOPEX = 0;
                let realizedCash = 0;
                let unpaidDebt = 0;

                // Process Income
                incomeItems.forEach(item => {
                    if (!item.date) return;
                    
                    const key = getPeriodKey(item.date);
                    if (!groups[key]) groups[key] = { revenue: 0, items: [] };
                    
                    const discount = parseFloat(item.discount || 0);
                    const deliveryFee = parseFloat(item.delivery_fee || 0);
                    const finalPaid = parseFloat(item.amount) - discount + deliveryFee;
                    
                    groups[key].revenue += finalPaid;
                    groups[key].items.push(item);
                    
                    totalRevenue += finalPaid;

                    // Cash Flow Tracking
                    const pMode = item.paymentMode || item.payment_mode || 'Cash';
                    if (pMode === 'Credit / Unpaid') {
                        unpaidDebt += finalPaid;
                    } else if (pMode === 'Split') {
                        const sCash = parseFloat(item.splitCash || item.split_cash || 0);
                        const sTrans = parseFloat(item.splitTransfer || item.split_transfer || 0);
                        const totalSplit = sCash + sTrans;
                        realizedCash += totalSplit;
                        if (totalSplit < finalPaid) unpaidDebt += (finalPaid - totalSplit);
                    } else {
                        realizedCash += finalPaid;
                    }
                });

                // Process Expenses
                expenseItems.forEach(item => {
                    if (!item.date) return;
                    const amount = parseFloat(item.amount || 0);
                    
                    // Identify category
                    const cat = item.category || '';
                    if (cat.includes('Inventory') || cat.includes('Materials')) {
                        totalCOGS += amount;
                    } else if (cat.includes("Owner's Draw")) {
                        // Personal draw: ignore from P&L
                    } else {
                        // Everything else is OPEX
                        totalOPEX += amount;
                    }
                });

                // Calculate Margins
                const grossProfit = totalRevenue - totalCOGS;
                const netProfit = grossProfit - totalOPEX;
                const netMargin = totalRevenue > 0 ? ((netProfit / totalRevenue) * 100).toFixed(0) : 0;

                // Update Metric Grid
                const f = (val) => `₦${val.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
                
                const elRev = document.getElementById('analytics-revenue');
                const elCogs = document.getElementById('analytics-cogs');
                const elGross = document.getElementById('analytics-gross-profit');
                const elOpex = document.getElementById('analytics-opex');
                const elCash = document.getElementById('analytics-cash');
                const elNet = document.getElementById('analytics-net-profit');
                const elMargin = document.getElementById('analytics-margin');

                if(elRev) elRev.textContent = f(totalRevenue);
                if(elCogs) elCogs.textContent = f(totalCOGS);
                if(elGross) elGross.textContent = f(grossProfit);
                if(elOpex) elOpex.textContent = f(totalOPEX);
                if(elCash) elCash.textContent = f(realizedCash);
                if(elNet) {
                    elNet.textContent = f(netProfit);
                    if (netProfit < 0) elNet.classList.replace('text-indigo-700', 'text-rose-600');
                    else elNet.classList.replace('text-rose-600', 'text-indigo-700');
                }
                if(elMargin) {
                    elMargin.textContent = `${netMargin}% Margin`;
                    if (netProfit < 0) {
                        elMargin.classList.replace('bg-indigo-100', 'bg-rose-100');
                        elMargin.classList.replace('text-indigo-700', 'text-rose-700');
                    } else {
                        elMargin.classList.replace('bg-rose-100', 'bg-indigo-100');
                        elMargin.classList.replace('text-rose-700', 'text-indigo-700');
                    }
                }

                // Update Narrative
                const narrativeEl = document.getElementById('analytics-narrative');
                if (narrativeEl) {
                    if (totalRevenue === 0 && totalOPEX === 0 && totalCOGS === 0) {
                        narrativeEl.innerHTML = "You have no financial data recorded for this period. Log sales or expenses to see insights.";
                    } else {
                        let text = `You sold <strong>${f(totalRevenue)}</strong> across the selected period. `;
                        text += `It cost you <strong>${f(totalCOGS)}</strong> to buy those goods (Gross Profit: <strong>${f(grossProfit)}</strong>). `;
                        text += `You spent <strong>${f(totalOPEX)}</strong> on operating overhead (transport, data, fuel). `;
                        text += `Your Net Profit is <strong>${f(netProfit)}</strong> (<strong>${netMargin}%</strong> Net Margin). `;
                        
                        if (unpaidDebt > 0) {
                            text += `<br><br><span class="text-amber-700">However, <strong>${f(unpaidDebt)}</strong> is still owed to you by customers.</span> You have <strong>${f(realizedCash)}</strong> in liquid cash right now.`;
                        } else {
                            text += `<br><br>All sales were paid. You have <strong>${f(realizedCash)}</strong> in liquid cash right now.`;
                        }
                        narrativeEl.innerHTML = text;
                    }
                }

                // Render List
                const listEl = document.getElementById('analytics-grouped-list');
                const labelEl = document.getElementById('analytics-period-label');
                
                const labels = { 'daily': 'Per Day', 'weekly': 'Per Week', 'monthly': 'Per Month', 'yearly': 'Per Year' };
                if(labelEl) labelEl.textContent = labels[period];

                if (Object.keys(groups).length === 0) {
                    listEl.innerHTML = '<p class="text-center text-gray-400 py-8 text-sm">No sales data available.</p>';
                    return;
                }

                // Sort keys (newest first roughly)
                const sortedKeys = Object.keys(groups).sort((a, b) => new Date(b) - new Date(a));

                listEl.innerHTML = sortedKeys.map(key => {
                    const g = groups[key];
                    return `
                    <details class="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden group">
                        <summary class="p-4 flex items-center justify-between cursor-pointer list-none outline-none">
                            <div class="flex items-center gap-2">
                                <svg class="w-4 h-4 text-gray-400 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg>
                                <span class="font-bold text-gray-800 text-sm">${key}</span>
                                <span class="text-[10px] bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full font-bold">${g.items.length} tx</span>
                            </div>
                            <span class="font-bold text-indigo-600">₦${g.revenue.toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                        </summary>
                        <div class="px-4 pb-4 pt-1 space-y-2 bg-white">
                            ${g.items.map(item => {
                                const discount = parseFloat(item.discount || 0);
                                const deliveryFee = parseFloat(item.delivery_fee || 0);
                                const finalPaid = parseFloat(item.amount) - discount + deliveryFee;
                                const receiptBadge = item.receipt_id ? `<span class="text-[9px] text-gray-400 font-mono ml-1">#${item.receipt_id}</span>` : '';
                                return `
                                <div class="flex justify-between items-center text-xs py-1 border-b border-gray-50 last:border-0">
                                    <div>
                                        <p class="font-semibold text-gray-700">${item.item_sold}</p>
                                        <p class="text-[10px] text-gray-400">${item.customer_name || 'Walk-in'} ${receiptBadge}</p>
                                    </div>
                                    <div class="text-right">
                                        <p class="font-bold text-emerald-600">₦${finalPaid.toLocaleString('en-US', {minimumFractionDigits: 2})}</p>
                                    </div>
                                </div>
                                `;
                            }).join('')}
                        </div>
                    </details>
                    `;
                }).join('');
            }

            // Initial calculations and renders
            renderIncomeListUI();
            calculateDashboard();
            if (navigator.onLine) {
                syncAllPendingData();
            }
            syncIncomeFromServer();

            // -------------------------------------------------------------
            // TRANSACTION FILTER — DOM-based, category & amount only
            // Description field is never read or compared.
            // -------------------------------------------------------------
            function applyTransactionFilter() {
                const categoryVal  = document.getElementById('filter-category')?.value || '';
                const amountVal    = document.getElementById('filter-amount-exact')?.value;
                const exactAmount  = amountVal !== '' && amountVal != null ? parseFloat(amountVal) : null;
                const isFiltered   = categoryVal !== '' || exactAmount !== null;

                const cards        = document.querySelectorAll('#transaction-list .expense-card');
                const noMatch      = document.getElementById('filter-no-match');
                const clearBtn     = document.getElementById('btn-clear-filters');
                let visibleCount   = 0;
                let filteredTotal  = 0;

                cards.forEach(card => {
                    const cardCategory = card.dataset.category || '';
                    const cardAmount   = parseFloat(card.dataset.amount || 0);

                    const categoryMatch = categoryVal === '' || cardCategory === categoryVal;
                    const amountMatch   = exactAmount === null || Math.abs(cardAmount - exactAmount) < 0.001;

                    if (categoryMatch && amountMatch) {
                        card.style.display = '';
                        filteredTotal += cardAmount;
                        visibleCount++;
                    } else {
                        card.style.display = 'none';
                    }
                });

                // Toggle "no match" empty state
                if (noMatch) noMatch.classList.toggle('hidden', visibleCount > 0 || !isFiltered);

                // Toggle clear button
                if (clearBtn) clearBtn.classList.toggle('hidden', !isFiltered);

                // Update filter result banner
                const banner      = document.getElementById('filter-result-banner');
                const bannerTotal = document.getElementById('filter-result-total');
                const bannerLabel = document.getElementById('filter-result-label');
                const matchCount  = document.getElementById('filter-match-count');

                if (isFiltered && banner) {
                    const parts = [];
                    if (categoryVal) parts.push(categoryVal);
                    if (exactAmount !== null) parts.push(`\u20a6${exactAmount.toLocaleString()}`);
                    if (bannerLabel) bannerLabel.textContent = 'Filtered: ' + parts.join(' \u00b7 ');
                    if (bannerTotal) bannerTotal.textContent = '\u20a6' + filteredTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    if (matchCount)  matchCount.textContent  = `${visibleCount} result${visibleCount !== 1 ? 's' : ''}`;
                    banner.classList.remove('hidden');
                } else if (banner) {
                    banner.classList.add('hidden');
                }

                // NOTE: Dashboard CFO cards (cfo-total-expenses etc.) are intentionally
                // NOT updated here. Filters only affect the filter-result-banner below.
                // Dashboard totals are only recalculated when real transactions are saved.
            }

            // Recalculates CFO cards using the visible expense total.
            // Pass null to use full IndexedDB grand totals.
            function recalculateDashboard(filteredExpenseTotal) {
                if (filteredExpenseTotal === null) {
                    // No active filter — recompute grand totals from IndexedDB
                    calculateDashboard();
                    return;
                }

                // Use filtered expense total and keep full sales total
                openIndexedDB().then(db => {
                    const tx  = db.transaction(INCOME_STORE, 'readonly');
                    const req = tx.objectStore(INCOME_STORE).getAll();
                    req.onsuccess = () => {
                        const totalSales = (req.result || [])
                            .filter(i => !i.pending_delete)
                            .reduce((sum, i) => sum + parseFloat(i.amount || 0), 0);

                        const netProfit = totalSales - filteredExpenseTotal;
                        const fmt = v => '\u20a6' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

                        const salesEl     = document.getElementById('top-sales') || document.getElementById('cfo-total-sales');
                        const expensesEl  = document.getElementById('top-expenses') || document.getElementById('cfo-total-expenses');
                        const netProfitEl = document.getElementById('top-profit') || document.getElementById('cfo-net-profit');

                        if (salesEl)    salesEl.textContent    = fmt(totalSales);
                        if (expensesEl) expensesEl.textContent = fmt(filteredExpenseTotal);
                        if (netProfitEl) {
                            netProfitEl.textContent = fmt(netProfit);
                            netProfitEl.className   = netProfit < 0
                                ? 'text-sm font-extrabold text-rose-700 mt-0.5'
                                : 'text-sm font-extrabold text-indigo-800 mt-0.5';
                        }
                    };
                }).catch(err => console.warn('recalculateDashboard error:', err));
            }

            const filterCategory    = document.getElementById('filter-category');
            const filterAmountExact = document.getElementById('filter-amount-exact');
            const clearFiltersBtn   = document.getElementById('btn-clear-filters');

            if (filterCategory)    filterCategory.addEventListener('change', applyTransactionFilter);
            if (filterAmountExact) filterAmountExact.addEventListener('input', applyTransactionFilter);

            if (clearFiltersBtn) {
                clearFiltersBtn.addEventListener('click', () => {
                    if (filterCategory)    filterCategory.value    = '';
                    if (filterAmountExact) filterAmountExact.value = '';
                    applyTransactionFilter();
                });
            }

            // -------------------------------------------------------------
            // BUSINESS PROFILE UI HANDLERS & DIGITAL CARD ACTIONS
            // -------------------------------------------------------------
            function toggleProfileMode(mode) {
                const viewContainer = document.getElementById('profile-view-mode');
                const editContainer = document.getElementById('profile-edit-mode');
                if (!viewContainer || !editContainer) return;

                if (mode === 'edit') {
                    viewContainer.classList.add('hidden');
                    editContainer.classList.remove('hidden');
                } else {
                    editContainer.classList.add('hidden');
                    viewContainer.classList.remove('hidden');
                }
            }

            window.toggleProfileMode = toggleProfileMode;

            // 1. Helper function to capture the card
            async function generateCardCanvas() {
                const cardElement = document.querySelector("#digital-business-card");
                return await html2canvas(cardElement, { 
                    scale: 2,
                    useCORS: true,
                    backgroundColor: "#ffffff"
                });
            }

            // 2. The Native OS Share Action
            async function shareBusinessCard() {
                try {
                    const canvas = await generateCardCanvas();
                    const profile = window.SOLOBIZ_PROFILE || {};
                    const displayName = profile.company_name || document.getElementById('card-company-name')?.textContent?.trim() || 'SoloBiz Vendor';
                    
                    canvas.toBlob(async (blob) => {
                        const safeFileName = displayName.toLowerCase().replace(/[^a-z0-9]/g, '_');
                        const file = new File([blob], `${safeFileName}_business_card.png`, { type: "image/png" });
                        const storeSlug = profile.store_slug || '';
                        const storeLink = storeSlug ? `\n🌐 View storefront: https://solobiz.dev/store/${storeSlug}` : '';

                        if (navigator.canShare && navigator.canShare({ files: [file] })) {
                            try {
                                await navigator.share({
                                    title: `${displayName} — Business Card`,
                                    text: `Here is my business card for ${displayName}!${storeLink}`,
                                    files: [file]
                                });
                            } catch (error) {
                                console.log('Share window closed by user.');
                            }
                        } else {
                            // Fallback: download the card
                            const link = document.createElement('a');
                            link.download = `${safeFileName}_business_card.png`;
                            link.href = canvas.toDataURL('image/png');
                            link.click();
                        }
                    }, "image/png");
                } catch (error) {
                    console.error("Error generating the card for sharing:", error);
                }
            }

            // 3. The Direct Download Action
            async function downloadBusinessCard() {
                try {
                    const canvas = await generateCardCanvas();
                    const companyName = (document.getElementById('card-company-name')?.textContent || 'solobiz').trim().toLowerCase().replace(/[^a-z0-9]/g, '_');
                    const link = document.createElement("a");
                    link.download = `${companyName}_card.png`;
                    link.href = canvas.toDataURL("image/png");
                    link.click();
                } catch (error) {
                    console.error("Error downloading the card:", error);
                    alert("Something went wrong while downloading the card.");
                }
            }

            window.generateCardCanvas = generateCardCanvas;
            window.shareBusinessCard = shareBusinessCard;
            window.downloadBusinessCard = downloadBusinessCard;

            window.copyStorefrontLink = function() {
                const urlEl = document.getElementById('card-store-url');
                const slug = window.SOLOBIZ_PROFILE?.store_slug || 'your-store';
                const fullUrl = `https://solobiz.dev/store/${slug}`;

                navigator.clipboard.writeText(fullUrl).then(() => {
                    const btn = document.querySelector('[onclick="copyStorefrontLink()"]');
                    if (btn) {
                        const origHTML = btn.innerHTML;
                        btn.innerHTML = '✓ Copied!';
                        btn.classList.add('bg-emerald-600');
                        setTimeout(() => {
                            btn.innerHTML = origHTML;
                            btn.classList.remove('bg-emerald-600');
                        }, 2000);
                    }
                }).catch(err => {
                    console.error('Copy storefront link failed:', err);
                });
            };

            function highlightActiveSwatch(colorHex) {
                const targetColor = (colorHex || '#4F46E5').toUpperCase();
                const swatches = document.querySelectorAll('.palette-swatch');
                swatches.forEach(swatch => {
                    const swatchColor = (swatch.getAttribute('data-color') || '').toUpperCase();
                    if (swatchColor === targetColor) {
                        swatch.className = 'palette-swatch w-9 h-9 rounded-full ring-2 ring-offset-2 ring-slate-900 scale-110 shadow-md transition cursor-pointer flex items-center justify-center text-white text-xs font-bold';
                        swatch.style.backgroundColor = swatchColor;
                        swatch.innerHTML = '✓';
                    } else {
                        swatch.className = 'palette-swatch w-9 h-9 rounded-full ring-2 ring-offset-2 ring-transparent opacity-80 hover:opacity-100 hover:scale-105 transition cursor-pointer flex items-center justify-center text-white text-xs font-bold shadow-sm';
                        swatch.style.backgroundColor = swatchColor;
                        swatch.innerHTML = '';
                    }
                });
            }

            function updateCardThemeColor(colorHex) {
                const color = colorHex || '#4F46E5';
                const hiddenInput = document.getElementById('profile-brand-color');
                if (hiddenInput) hiddenInput.value = color;

                const accentBar = document.getElementById('card-top-accent');
                if (accentBar) accentBar.style.backgroundColor = color;

                const logoContainer = document.getElementById('card-logo-container');
                if (logoContainer) logoContainer.style.backgroundColor = color;

                highlightActiveSwatch(color);
            }

            // Attach swatch click events
            document.querySelectorAll('.palette-swatch').forEach(swatch => {
                swatch.addEventListener('click', (e) => {
                    const selectedColor = e.currentTarget.getAttribute('data-color');
                    if (selectedColor) updateCardThemeColor(selectedColor);
                });
            });

            async function populateProfileFormUI() {
                const profile = await loadBusinessProfile();

                // Form Inputs
                const compEl = document.getElementById('profile-company-name');
                const phoneEl = document.getElementById('profile-business-phone');
                const waEl = document.getElementById('profile-whatsapp-number');
                const igEl = document.getElementById('profile-instagram-handle');
                const addrEl = document.getElementById('profile-business-address');
                const polEl = document.getElementById('profile-store-policy');
                const colorEl = document.getElementById('profile-brand-color');

                // Card Elements
                const cComp = document.getElementById('card-company-name');
                const cPhone = document.getElementById('card-phone');
                const cAddr = document.getElementById('card-address');
                const cWaPill = document.getElementById('card-whatsapp-pill');
                const cWa = document.getElementById('card-whatsapp');
                const cIgPill = document.getElementById('card-instagram-pill');
                const cIg = document.getElementById('card-instagram');
                const cPolBox = document.getElementById('card-policy-box');
                const cPolText = document.getElementById('card-policy-text');
                const cStoreUrl = document.getElementById('card-store-url');
                const cVisitBtn = document.getElementById('card-store-visit-btn');
                const logoContainer = document.getElementById('card-logo-container');

                // Preview Card
                const pComp = document.getElementById('preview-company-name');
                const pPhone = document.getElementById('preview-business-phone');
                const pAddr = document.getElementById('preview-business-address');

                if (profile && profile.company_name) {
                    if (compEl) compEl.value = profile.company_name || '';
                    if (phoneEl) phoneEl.value = profile.business_phone || '';
                    if (waEl) waEl.value = profile.whatsapp_number || '';
                    if (igEl) igEl.value = profile.instagram_handle || '';
                    if (addrEl) addrEl.value = profile.business_address || '';
                    if (polEl) polEl.value = profile.store_policy || '';
                    if (colorEl) colorEl.value = profile.brand_color || '#4F46E5';

                    updateCardThemeColor(profile.brand_color || '#4F46E5');

                    if (cComp) cComp.childNodes[0].nodeValue = profile.company_name + ' ';
                    if (cPhone) cPhone.textContent = profile.business_phone || 'Not set';
                    if (cAddr) cAddr.textContent = profile.business_address || 'Not set';

                    // WhatsApp Pill
                    if (cWaPill && cWa) {
                        if (profile.whatsapp_number) {
                            cWa.textContent = profile.whatsapp_number;
                            cWaPill.classList.remove('hidden');
                        } else {
                            cWaPill.classList.add('hidden');
                        }
                    }

                    // Instagram Pill
                    if (cIgPill && cIg) {
                        if (profile.instagram_handle) {
                            cIg.textContent = profile.instagram_handle.startsWith('@') ? profile.instagram_handle : '@' + profile.instagram_handle;
                            cIgPill.classList.remove('hidden');
                        } else {
                            cIgPill.classList.add('hidden');
                        }
                    }

                    // Policy Box
                    if (cPolBox && cPolText) {
                        if (profile.store_policy) {
                            cPolText.textContent = `"${profile.store_policy}"`;
                            cPolBox.classList.remove('hidden');
                        } else {
                            cPolBox.classList.add('hidden');
                        }
                    }

                    // Store URL Badge
                    const slug = profile.store_slug || 'your-store';
                    if (cStoreUrl) cStoreUrl.textContent = `solobiz.dev/store/${slug}`;
                    if (cVisitBtn) cVisitBtn.href = `/store/${slug}`;

                    // Logo Container Image vs Letter Initial
                    if (logoContainer) {
                        if (profile.logo_url) {
                            logoContainer.innerHTML = `<img id="card-logo-img" src="${profile.logo_url}" alt="Logo" class="w-full h-full object-cover">`;
                        } else {
                            const initChar = (profile.company_name || 'B').trim().charAt(0).toUpperCase();
                            logoContainer.innerHTML = `<span id="card-logo-initial">${initChar}</span>`;
                        }
                    }

                    if (pComp) pComp.textContent = profile.company_name;
                    if (pPhone) pPhone.textContent = profile.business_phone || '+234 000 000 0000';
                    if (pAddr) pAddr.textContent = profile.business_address || 'Business Address Preview';

                    // ── Dynamic App Branding: Profile UI populated ──────
                    toggleProfileMode('view');
                } else {
                    updateCardThemeColor('#4F46E5');
                    toggleProfileMode('edit');
                }
            }

            const btnEditProfile = document.getElementById('btn-edit-profile');
            if (btnEditProfile) {
                btnEditProfile.addEventListener('click', () => toggleProfileMode('edit'));
            }

            const btnCancelProfile = document.getElementById('btn-cancel-profile');
            if (btnCancelProfile) {
                btnCancelProfile.addEventListener('click', () => toggleProfileMode('view'));
            }

            const profileForm = document.getElementById('profile-form');
            let pendingProfileFormData = null;

            if (profileForm) {
                profileForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const saveBtn = document.getElementById('btn-save-profile');
                    if (saveBtn) {
                        saveBtn.disabled = true;
                        saveBtn.innerHTML = 'Requesting Code...';
                    }

                    try {
                        pendingProfileFormData = new FormData(profileForm);
                        
                        // Request OTP
                        const response = await authenticatedFetch('/api/business_profile/request-otp', {
                            method: 'POST'
                        });
                        const data = await response.json();
                        
                        if (response.ok && data.status === 'success') {
                            document.getElementById('profile-otp-modal').classList.remove('hidden');
                        } else {
                            throw new Error(data.message || 'Failed to request code');
                        }
                    } catch (err) {
                        console.error('OTP request error:', err);
                        alert('Error requesting verification code: ' + (err.message || 'Network issue'));
                    } finally {
                        if (saveBtn) {
                            saveBtn.disabled = false;
                            saveBtn.innerHTML = 'Save Profile';
                        }
                    }
                });
            }

            const otpForm = document.getElementById('profile-otp-form');
            if (otpForm) {
                otpForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    if (!pendingProfileFormData) return;
                    
                    const otpInput = document.getElementById('profile-otp-input').value;
                    pendingProfileFormData.set('otp', otpInput);
                    
                    const verifyBtn = document.getElementById('btn-verify-otp');
                    if (verifyBtn) {
                        verifyBtn.disabled = true;
                        verifyBtn.innerHTML = 'Verifying...';
                    }

                    try {
                        await saveBusinessProfile(pendingProfileFormData);
                        await populateProfileFormUI();

                        const statusMsg = document.getElementById('profile-status-msg');
                        if (statusMsg) {
                            statusMsg.classList.remove('hidden');
                            setTimeout(() => statusMsg.classList.add('hidden'), 3500);
                        }

                        document.getElementById('profile-otp-modal').classList.add('hidden');
                        otpForm.reset();
                        toggleProfileMode('view');
                    } catch (err) {
                        console.error('Save profile error:', err);
                        alert('Error saving profile: ' + (err.message || 'Invalid code'));
                    } finally {
                        if (verifyBtn) {
                            verifyBtn.disabled = false;
                            verifyBtn.innerHTML = 'Verify & Save';
                        }
                    }
                });
            }

            // Pre-fill profile form on load
            populateProfileFormUI();
        });
    