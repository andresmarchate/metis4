document.addEventListener('DOMContentLoaded', () => {
    console.log('main.js loaded successfully');

    // Select DOM elements
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const minRelevanceInput = document.getElementById('min-relevance');
    const clearCacheInput = document.getElementById('clear-cache');
    const resultsTable = document.getElementById('results-table');
    const resultsBody = document.getElementById('results-body');
    const resultsCount = document.getElementById('results-count');
    const noResults = document.getElementById('no-results');
    const pagination = document.getElementById('pagination');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const pageNumbersSpan = document.getElementById('page-numbers');
    let modal = document.getElementById('email-modal');
    let modalContent = document.getElementById('email-details');
    let closeModal = document.querySelector('.close');
    const notRelevantBtn = document.getElementById('not-relevant');
    const filterPrompt = document.getElementById('filter-prompt');
    const applyFilterBtn = document.getElementById('apply-filter');
    const resetFiltersBtn = document.getElementById('reset-filters');
    const filtersList = document.getElementById('filters-list');
    const errorMessage = document.getElementById('error-message');
    const analyzeThemesBtn = document.getElementById('analyze-themes');
    const searchSection = document.getElementById('search-section');
    const themesSection = document.getElementById('themes-section');
    const themesList = document.getElementById('themes-list');

    let currentQuery = '';
    let currentMinRelevance = 10;
    let currentPage = 1;
    let totalPages = 1;
    const resultsPerPage = 25;
    let filterCounts = { remove: {}, add: {} };
    let currentEmails = []; // Array of { message_id, index }

    // Fallback for missing email-modal
    if (!modal || !modalContent || !closeModal) {
        console.warn('Email modal elements not found, creating dynamically');
        modal = document.createElement('div');
        modal.id = 'email-modal';
        modal.className = 'modal';
        modal.style.display = 'none';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="close">×</span>
                <div id="email-details"></div>
                <button id="not-relevant">Marcar como No Relevante</button>
            </div>
        `;
        document.body.appendChild(modal);
        modalContent = document.getElementById('email-details');
        closeModal = modal.querySelector('.close');
        notRelevantBtn.dataset.id = document.getElementById('not-relevant');
    }

    if (!form) {
        console.error('Search form not found');
        return;
    }
    if (!filtersList) {
        console.error('Filters list element not found');
        return;
    }
    if (!analyzeThemesBtn || !themesSection || !themesList) {
        console.error('Themes analysis elements not found');
        return;
    }

    // Tab navigation functions
    function hideAllTabs() {
        console.log('Hiding all tabs');
        if (searchSection) searchSection.style.display = 'none';
        if (themesSection) themesSection.style.display = 'none';
        document.querySelectorAll('.tab-link').forEach(link => {
            link.classList.remove('active');
        });
    }

    function showTab(tabId) {
        console.log('Showing tab:', tabId);
        hideAllTabs();
        if (tabId === 'consultas') {
            if (searchSection) searchSection.style.display = 'block';
            document.querySelector('.tab-link[data-tab="consultas"]')?.classList.add('active');
        } else if (tabId === 'themes') {
            if (themesSection) themesSection.style.display = 'block';
            document.querySelector('.tab-link[data-tab="themes"]')?.classList.add('active');
        }
    }

    function normalizeText(text) {
        if (!text || typeof text !== 'string') return text;
        return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    }

    function escapeHtml(unsafe, isMessageId = false) {
        if (!unsafe) return 'N/A';
        let safe = typeof unsafe === 'string' ? unsafe : String(unsafe);
        console.log('Escaping HTML:', { unsafe, isMessageId });

        if (isMessageId || safe.match(/<[^>]+@[^>]+>/)) {
            console.log('Preserving email format:', safe);
            return safe;
        }

        console.log('Escaping non-email text:', safe);
        return safe
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function parseFilterPrompt(prompt) {
        if (!prompt || typeof prompt !== 'string') return null;
        const normalizedPrompt = normalizeText(prompt.trim());
        const removeMatch = normalizedPrompt.match(/^(elimina|excluye|remove|delete)\s+correos\s+que\s+incluyan\s+(.+)/i);
        const addMatch = normalizedPrompt.match(/^(anade|añade|agrega|incluye|add|include)\s+correos\s+que\s+incluyan\s+(.+)/i);

        if (removeMatch) {
            const terms = removeMatch[2].split(/\s*,\s*/).map(term => term.trim()).filter(term => term);
            console.log('Parsed remove filter terms:', terms);
            return { action: 'remove', terms };
        } else if (addMatch) {
            const terms = addMatch[2].split(/\s*,\s*/).map(term => term.trim()).filter(term => term);
            console.log('Parsed add filter terms:', terms);
            return { action: 'add', terms };
        }
        console.warn('Invalid prompt format:', normalizedPrompt);
        return null;
    }

    function renderFilters(filters, counts = { remove: {}, add: {} }) {
        console.log('Rendering filters:', filters, 'with counts:', counts);
        if (!filtersList) {
            console.error('filtersList element not found');
            return;
        }
        filtersList.innerHTML = '';
        if (!Array.isArray(filters) || filters.length === 0) {
            console.log('No filters to render');
            return;
        }
        filters.forEach((filter, index) => {
            console.log('Creating filter item:', { filter, index });
            const li = document.createElement('li');
            const actionText = filter.action === 'remove' ? 'Eliminar' : 'Añadir';
            const termsText = escapeHtml(filter.terms.join(', '));
            const termsKey = filter.terms.join(', ');
            const count = filter.action === 'remove' ? counts.remove[termsKey] || 0 : counts.add[termsKey] || 0;
            const countText = filter.action === 'remove' ? `(<a href="#" class="filter-count-link" data-index="${index}">${count} correos eliminados</a>)` : `(<a href="#" class="filter-count-link" data-index="${index}">${count} correos añadidos</a>)`;
            li.innerHTML = `${actionText}: ${termsText} ${countText}`;

            const removeBtn = document.createElement('button');
            removeBtn.textContent = 'X';
            removeBtn.className = 'remove-filter';
            removeBtn.onclick = () => removeFilter(index);
            li.appendChild(removeBtn);

            const notRelevantBtn = document.createElement('button');
            notRelevantBtn.textContent = 'Marcar como No Relevantes';
            notRelevantBtn.className = 'not-relevant-filter';
            notRelevantBtn.onclick = () => markFilterAsNotRelevant(filter, index);
            li.appendChild(notRelevantBtn);

            filtersList.appendChild(li);

            // Add event listener for filter count link
            li.querySelector('.filter-count-link').addEventListener('click', (e) => {
                e.preventDefault();
                console.log('Filter count link clicked:', { filter, index });
                showFilterEmailsModal(filter);
            });
        });
    }

    async function showFilterEmailsModal(filter) {
        console.log('Fetching emails for filter:', filter);
        try {
            const response = await fetch('/api/filter_emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: currentQuery,
                    filter: filter,
                    page: 1,
                    results_per_page: 25
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Filter emails response:', data);
            console.log('Emails in filter modal:', data.results.map(email => ({
                message_id: email.message_id,
                index: email.index,
                subject: email.subject,
                relevant_terms: email.relevant_terms || [],
                description: email.description,
                explanation: email.explanation
            })));

            const filterModal = document.createElement('div');
            filterModal.className = 'modal';
            filterModal.style.display = 'flex';
            filterModal.innerHTML = `
                <div class="modal-content">
                    <span class="close">×</span>
                    <h2>Correos ${filter.action === 'remove' ? 'Eliminados' : 'Añadidos'} por el Filtro: ${escapeHtml(filter.terms.join(', '))}</h2>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Índice</th>
                                    <th>Fecha</th>
                                    <th>Asunto</th>
                                    <th>Remitente</th>
                                    <th>Destinatario</th>
                                    <th>Descripción</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.results.map(email => `
                                    <tr>
                                        <td>${escapeHtml(email.index || 'N/A')}</td>
                                        <td>${escapeHtml(new Date(email.date).toLocaleString())}</td>
                                        <td>${escapeHtml(email.subject)}</td>
                                        <td>${escapeHtml(email.from)}</td>
                                        <td>${escapeHtml(email.to)}</td>
                                        <td>${escapeHtml(email.description)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
            document.body.appendChild(filterModal);

            filterModal.querySelector('.close').addEventListener('click', () => {
                console.log('Closing filter modal');
                filterModal.remove();
            });
            filterModal.addEventListener('click', (e) => {
                if (e.target === filterModal) {
                    console.log('Closing filter modal via background click');
                    filterModal.remove();
                }
            });
        } catch (error) {
            console.error('Error fetching filter emails:', error);
            alert('Error al cargar los correos del filtro: ' + error.message);
        }
    }

    function removeFilter(index) {
        console.log('Removing filter at index:', index);
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        filters.splice(index, 1);
        sessionStorage.setItem('filters', JSON.stringify(filters));
        renderFilters(filters, filterCounts);
        performSearch();
    }

    async function markFilterAsNotRelevant(filter, index) {
        console.log('Marking emails for filter as not relevant:', filter);
        try {
            const response = await fetch('/api/bulk_feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: currentQuery,
                    filter: {
                        action: filter.action,
                        terms: filter.terms
                    }
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('Bulk feedback response:', result);
            alert(`Se marcaron ${result.affected_count} correos como no relevantes.`);
            performSearch();
        } catch (err) {
            console.error('Error sending bulk feedback:', err);
            alert('Error al marcar correos como no relevantes: ' + err.message);
        }
    }

    function updatePagination(totalResults) {
        totalPages = Math.ceil(totalResults / resultsPerPage);
        console.log('Total results:', totalResults, 'Total pages:', totalPages);

        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages || totalPages === 0;

        let pageNumbers = '';
        const maxPagesToShow = 10;
        let startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

        if (endPage - startPage + 1 < maxPagesToShow) {
            startPage = Math.max(1, endPage - maxPagesToShow + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            if (i === currentPage) {
                pageNumbers += `<span class="current-page">${i}</span>`;
            } else {
                pageNumbers += `<a href="#" class="page-link" data-page="${i}">${i}</a>`;
            }
        }
        pageNumbersSpan.innerHTML = pageNumbers;

        document.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                currentPage = parseInt(e.target.dataset.page);
                performSearch();
            });
        });

        pagination.style.display = totalResults > 0 ? 'block' : 'none';
    }

    function renderThemes(themes) {
        console.log('Rendering themes:', themes);
        themesList.innerHTML = '';
        if (!Array.isArray(themes) || themes.length === 0) {
            console.log('No themes to render');
            themesSection.innerHTML = '<p>No se identificaron temas.</p>';
            themesSection.style.display = 'block';
            return;
        }

        themes.forEach(theme => {
            // Format summary as list or paragraph
            let summaryHtml = '';
            if (Array.isArray(theme.summary)) {
                summaryHtml = `<ul class="theme-summary">${theme.summary.map(point => `<li>${escapeHtml(point)}</li>`).join('')}</ul>`;
            } else if (typeof theme.summary === 'string') {
                const points = theme.summary.split(/[\n,]+/).map(p => p.trim()).filter(p => p);
                if (points.length > 1) {
                    summaryHtml = `<ul class="theme-summary">${points.map(point => `<li>${escapeHtml(point)}</li>`).join('')}</ul>`;
                } else {
                    summaryHtml = `<p class="theme-summary">${escapeHtml(theme.summary || 'No hay resumen disponible.')}</p>`;
                }
            } else {
                summaryHtml = `<p class="theme-summary">No hay resumen disponible.</p>`;
            }

            const detail = document.createElement('details');
            detail.innerHTML = `
                <summary>
                    <strong>${escapeHtml(theme.title)}</strong> (${theme.emails.length} correos, Estado: ${escapeHtml(theme.status)})
                </summary>
                <h3>Resumen del Tema</h3>
                ${summaryHtml}
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Índice</th>
                                <th>Fecha</th>
                                <th>Remitente</th>
                                <th>Asunto</th>
                                <th>Descripción</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${theme.emails.map(email => `
                                <tr>
                                    <td><a href="#" class="theme-email-link" data-index="${escapeHtml(email.index || email.message_id || 'N/A')}">${escapeHtml(email.index || email.message_id || 'N/A')}</a></td>
                                    <td>${escapeHtml(email.date ? new Date(email.date).toLocaleString() : 'N/A')}</td>
                                    <td>${escapeHtml(email.from)}</td>
                                    <td>${escapeHtml(email.subject)}</td>
                                    <td>${escapeHtml(email.description?.slice(0, 100))}${email.description?.length > 100 ? '...' : ''}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
            themesList.appendChild(detail);

            // Add event listeners for email links
            detail.querySelectorAll('.theme-email-link').forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = e.target.dataset.index;
                    console.log('Clicked theme email link with identifier:', identifier);
                    if (!identifier || identifier === 'N/A') {
                        console.error('No valid identifier found for link:', e.target);
                        alert('Identificador de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Fetching email details for identifier:', identifier);
                        const response = await fetch(`/api/email?index=${encodeURIComponent(identifier)}`);
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const email = await response.json();
                        console.log('Email details:', email);
                        const attachmentsContent = Array.isArray(email.attachments_content)
                            ? email.attachments_content.join('\n')
                            : email.attachments_content || '';
                        modalContent.innerHTML = `
                            <p><strong>Índice:</strong> ${escapeHtml(email.index || 'N/A')}</p>
                            <p><strong>ID:</strong> ${escapeHtml(email.message_id || 'N/A', true)}</p>
                            <p><strong>De:</strong> ${escapeHtml(email.from || 'N/A')}</p>
                            <p><strong>Para:</strong> ${escapeHtml(email.to || 'N/A')}</p>
                            <p><strong>Asunto:</strong> ${escapeHtml(email.subject || '')}</p>
                            <p><strong>Fecha:</strong> ${escapeHtml(email.date || '')}</p>
                            <p><strong>Resumen:</strong> ${escapeHtml(email.summary || 'N/A')}</p>
                            <p><strong>Cuerpo:</strong> ${escapeHtml(email.body || '')}</p>
                            <p><strong>Adjuntos:</strong> ${escapeHtml(attachmentsContent)}</p>
                        `;
                        modal.style.display = 'flex';
                        notRelevantBtn.dataset.id = email.message_id || email.index;
                    } catch (err) {
                        console.error('Error fetching email:', err);
                        alert('Error al cargar los detalles del correo: ' + err.message);
                    }
                });
            });
        });
        themesSection.style.display = 'block';
    }

    async function performSearch() {
        const query = queryInput.value.trim();
        const minRelevance = parseInt(minRelevanceInput.value) || 10;
        const clearCache = clearCacheInput.checked;
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        currentQuery = query;
        currentMinRelevance = Math.max(0, Math.min(minRelevance, 100));

        console.log('Performing search with filters:', filters);

        if (!query) {
            console.warn('Empty query submitted');
            errorMessage.textContent = 'Por favor, introduce una consulta.';
            errorMessage.style.display = 'block';
            return;
        }

        errorMessage.style.display = 'none';

        if (!sessionStorage.getItem('originalQuery')) {
            sessionStorage.setItem('originalQuery', query);
        } else if (clearCache && query !== sessionStorage.getItem('originalQuery')) {
            sessionStorage.setItem('originalQuery', query);
            sessionStorage.setItem('filters', JSON.stringify([]));
            filters = [];
            renderFilters(filters, filterCounts);
        }

        try {
            resultsBody.innerHTML = '';
            resultsTable.style.display = 'none';
            noResults.style.display = 'none';
            resultsCount.style.display = 'none';
            analyzeThemesBtn.style.display = 'none';
            showTab('consultas'); // Ensure Consultas tab is active

            console.log('Sending POST request to /api/search', { query, minRelevance: currentMinRelevance, page: currentPage, clearCache, filters });
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    minRelevance: currentMinRelevance,
                    page: currentPage,
                    resultsPerPage,
                    clearCache,
                    filters
                })
            });

            console.log('Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Search response:', data);

            const results = data.results || [];
            const totalResults = data.totalResults || 0;
            filterCounts = data.filter_counts || { remove: {}, add: {} };
            currentEmails = results.map(result => ({
                message_id: result.message_id,
                index: result.index
            })).filter(email => email.index || email.message_id);

            if (!Array.isArray(results) || results.length === 0) {
                console.log('No results returned');
                noResults.style.display = 'block';
                updatePagination(0);
                renderFilters(filters, filterCounts);
                return;
            }

            resultsCount.textContent = `Se han encontrado ${totalResults} correos relevantes`;
            resultsCount.style.display = 'block';
            analyzeThemesBtn.style.display = 'block';

            resultsTable.style.display = 'table';
            results.forEach(result => {
                console.log('Processing result:', { from: result.from, to: result.to });
                if (!result.message_id && !result.index) {
                    console.warn('Missing message_id and index in result:', result);
                }
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><a href="#" class="index-link" data-index="${escapeHtml(result.index || result.message_id || 'N/A')}">${escapeHtml(result.index || 'N/A')}</a></td>
                    <td>${escapeHtml(result.date || '')}</td>
                    <td>${escapeHtml(result.from || 'N/A')}</td>
                    <td>${escapeHtml(result.to || 'N/A')}</td>
                    <td>${escapeHtml(result.subject || '')}</td>
                    <td>${escapeHtml((result.description || '').slice(0, 100))}${result.description && result.description.length > 100 ? '...' : ''}</td>
                    <td>${escapeHtml((result.relevant_terms || []).join(', '))}</td>
                    <td>${result.relevance || ''}</td>
                    <td>${escapeHtml(result.explanation || '')}</td>
                    <td><button class="not-relevant" data-id="${escapeHtml(result.message_id || result.index || 'N/A')}">No Relevante</button></td>
                `;
                resultsBody.appendChild(row);
            });

            updatePagination(totalResults);
            renderFilters(filters, filterCounts);

            const indexLinks = document.querySelectorAll('.index-link');
            console.log('Found index links:', indexLinks.length);
            if (indexLinks.length === 0) {
                console.warn('No .index-link elements found');
            }
            indexLinks.forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = e.target.dataset.index;
                    console.log('Clicked index link with identifier:', identifier);
                    if (!identifier || identifier === 'N/A') {
                        console.error('No valid identifier found for link:', e.target);
                        alert('Identificador de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Fetching email details for identifier:', identifier);
                        const response = await fetch(`/api/email?index=${encodeURIComponent(identifier)}`);
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const email = await response.json();
                        console.log('Email details:', email);
                        const attachmentsContent = Array.isArray(email.attachments_content)
                            ? email.attachments_content.join('\n')
                            : email.attachments_content || '';
                        modalContent.innerHTML = `
                            <p><strong>Índice:</strong> ${escapeHtml(email.index || 'N/A')}</p>
                            <p><strong>ID:</strong> ${escapeHtml(email.message_id || 'N/A', true)}</p>
                            <p><strong>De:</strong> ${escapeHtml(email.from || 'N/A')}</p>
                            <p><strong>Para:</strong> ${escapeHtml(email.to || 'N/A')}</p>
                            <p><strong>Asunto:</strong> ${escapeHtml(email.subject || '')}</p>
                            <p><strong>Fecha:</strong> ${escapeHtml(email.date || '')}</p>
                            <p><strong>Resumen:</strong> ${escapeHtml(email.summary || 'N/A')}</p>
                            <p><strong>Cuerpo:</strong> ${escapeHtml(email.body || '')}</p>
                            <p><strong>Adjuntos:</strong> ${escapeHtml(attachmentsContent)}</p>
                        `;
                        modal.style.display = 'flex';
                        notRelevantBtn.dataset.id = email.message_id || email.index;
                    } catch (err) {
                        console.error('Error fetching email:', err);
                        alert('Error al cargar los detalles del correo: ' + err.message);
                    }
                });
            });

            const notRelevantButtons = document.querySelectorAll('.not-relevant');
            if (notRelevantButtons.length === 0) {
                console.warn('No .not-relevant buttons found');
            }
            notRelevantButtons.forEach(button => {
                button.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = button.dataset.id;
                    console.log('Clicked not-relevant button with identifier:', identifier);
                    if (!identifier || identifier === 'N/A') {
                        console.error('No valid identifier found for button:', button);
                        alert('Identificador de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Sending feedback for identifier:', identifier);
                        const response = await fetch('/api/feedback', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                query: currentQuery,
                                message_id: identifier,
                                is_relevant: false
                            })
                        });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        console.log('Feedback sent successfully');
                        alert('Retroalimentación enviada.');
                    } catch (err) {
                        console.error('Error sending feedback:', err);
                        alert('Error al enviar retroalimentación: ' + err.message);
                    }
                });
            });
        } catch (err) {
            console.error('Error during search:', err);
            errorMessage.textContent = 'Error al realizar la búsqueda: ' + err.message;
            errorMessage.style.display = 'block';
            updatePagination(0);
            renderFilters(filters, filterCounts);
        }
    }

    analyzeThemesBtn.addEventListener('click', async () => {
        if (!currentEmails || !Array.isArray(currentEmails) || currentEmails.length === 0) {
            console.warn('No valid emails to analyze', { currentEmails });
            errorMessage.textContent = 'No hay correos válidos para analizar temas.';
            errorMessage.style.display = 'block';
            return;
        }

        // Validate email identifiers
        const validEmails = currentEmails.filter(email => email.index || email.message_id);
        if (validEmails.length === 0) {
            console.warn('No valid email identifiers after filtering', { currentEmails });
            errorMessage.textContent = 'No hay identificadores de correos válidos para analizar.';
            errorMessage.style.display = 'block';
            return;
        }

        try {
            console.log('Sending theme analysis request for emails:', validEmails);
            const response = await fetch('/api/analyze_themes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email_ids: validEmails.map(email => email.message_id || email.index) })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error: ${response.status}` }));
                throw new Error(errorData.error || `HTTP error: ${response.status}`);
            }

            const data = await response.json();
            console.log('Theme analysis response:', data);
            if (data.error) {
                throw new Error(data.error);
            }
            renderThemes(data.themes || []);
            showTab('themes'); // Switch to Themes tab
        } catch (error) {
            console.error('Error analyzing themes:', error.message);
            errorMessage.textContent = `Error al analizar temas: ${error.message}`;
            errorMessage.style.display = 'block';
        }
    });

    prevPageBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            performSearch();
        }
    });

    nextPageBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            performSearch();
        }
    });

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        currentPage = 1;
        performSearch();
    });

    if (applyFilterBtn) {
        applyFilterBtn.addEventListener('click', () => {
            const prompt = filterPrompt.value.trim();
            console.log('Applying filter with prompt:', prompt);
            const filter = parseFilterPrompt(prompt);
            if (!filter || !filter.terms || filter.terms.length === 0) {
                console.warn('Invalid filter prompt:', prompt);
                errorMessage.textContent = 'Prompt inválido. Ejemplo: "elimina correos que incluyan reunión, proyecto" o "añade correos que incluyan respuesta, confirmación"';
                errorMessage.style.display = 'block';
                return;
            }
            errorMessage.textContent = '';
            errorMessage.style.display = 'none';
            let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
            filters.push(filter);
            console.log('Updated filters:', filters);
            sessionStorage.setItem('filters', JSON.stringify(filters));
            renderFilters(filters, filterCounts);
            filterPrompt.value = '';
            performSearch();
        });
    }

    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', () => {
            console.log('Resetting filters');
            sessionStorage.setItem('filters', JSON.stringify([]));
            filterCounts = { remove: {}, add: {} };
            renderFilters([], filterCounts);
            performSearch();
        });
    }

    if (closeModal) {
        closeModal.addEventListener('click', () => {
            console.log('Closing email modal');
            modal.style.display = 'none';
        });
    }

    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            console.log('Closing email modal via background click');
            modal.style.display = 'none';
        }
    });

    if (notRelevantBtn) {
        notRelevantBtn.addEventListener('click', async () => {
            const identifier = notRelevantBtn.dataset.id;
            console.log('Marking email as not relevant from modal:', identifier);
            if (!identifier || identifier === 'N/A') {
                console.error('No valid identifier found for modal feedback');
                alert('Identificador de correo no válido.');
                return;
            }
            try {
                const response = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: currentQuery,
                        message_id: identifier,
                        is_relevant: false
                    })
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                console.log('Feedback sent successfully');
                alert('Retroalimentación enviada.');
                modal.style.display = 'none';
            } catch (err) {
                console.error('Error sending feedback:', err);
                alert('Error al enviar retroalimentación: ' + err.message);
            }
        });
    }

    // Initialize tabs
    const tabLinks = document.querySelectorAll('.tab-link');
    tabLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = e.target.dataset.tab;
            console.log('Tab link clicked:', tabId);
            showTab(tabId);
        });
    });

    // Load initial state
    const initialFilters = JSON.parse(sessionStorage.getItem('filters') || '[]');
    console.log('Initial filters on load:', initialFilters);
    renderFilters(initialFilters, filterCounts);
    showTab('consultas'); // Show Consultas tab by default
});