const SearchModule = {
    init({ currentQuery, currentMinRelevance, currentPage, resultsPerPage, filterCounts, currentEmails, setCurrentEmails, setFilterCounts, setTotalPages }) {
        this.currentQuery = currentQuery;
        this.currentMinRelevance = currentMinRelevance;
        this.currentPage = currentPage;
        this.resultsPerPage = resultsPerPage;
        this.filterCounts = filterCounts || { remove: {}, add: {} };
        this.currentEmails = currentEmails || [];
        this.allEmailIds = []; // Nueva variable de estado para todos los IDs
        this.setCurrentEmails = setCurrentEmails;
        this.setExternalFilterCounts = setFilterCounts;
        this.setTotalPages = setTotalPages;
        this.totalPages = 1;

        this.form = document.getElementById('search-form');
        this.queryInput = document.getElementById('query');
        this.minRelevanceInput = document.getElementById('min-relevance');
        this.clearCacheInput = document.getElementById('clear-cache');
        this.resultsTable = document.getElementById('results-table');
        this.resultsBody = document.getElementById('results-body');
        this.resultsCount = document.getElementById('results-count');
        this.noResults = document.getElementById('no-results');
        this.pagination = document.getElementById('pagination');
        this.prevPageBtn = document.getElementById('prev-page');
        this.nextPageBtn = document.getElementById('next-page');
        this.pageNumbersSpan = document.getElementById('page-numbers');
        this.filterPrompt = document.getElementById('filter-prompt');
        this.applyFilterBtn = document.getElementById('apply-filter');
        this.resetFiltersBtn = document.getElementById('reset-filters');
        this.filtersList = document.getElementById('filters-list');
        this.errorMessage = document.getElementById('error-message');
        this.analyzeThemesBtn = document.getElementById('analyze-themes');
        this.searchSection = document.getElementById('consultas-section');

        console.log('SearchModule init: searchSection found:', !!this.searchSection);
        console.log('SearchModule init: filtersList found:', !!this.filtersList);

        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.currentPage = 1;
            console.log('Search form submitted');
            this.performSearch();
        });

        this.applyFilterBtn.addEventListener('click', () => {
            const filter = UtilsModule.parseFilterPrompt(this.filterPrompt.value);
            if (filter) {
                let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
                filters.push(filter);
                sessionStorage.setItem('filters', JSON.stringify(filters));
                this.filterPrompt.value = '';
                console.log('Applying filter:', filter);
                this.performSearch();
            } else {
                alert('Formato de filtro inválido. Usa "elimina correos que incluyan término1, término2" o "añade correos que incluyan término1, término2".');
            }
        });

        this.resetFiltersBtn.addEventListener('click', () => {
            sessionStorage.setItem('filters', JSON.stringify([]));
            this.filterPrompt.value = '';
            console.log('Resetting filters');
            this.performSearch();
        });

        this.prevPageBtn.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                console.log('Navigating to previous page:', this.currentPage);
                this.performSearch();
            }
        });

        this.nextPageBtn.addEventListener('click', () => {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
                console.log('Navigating to next page:', this.currentPage);
                this.performSearch();
            }
        });

        this.analyzeThemesBtn.addEventListener('click', async () => {
            console.log('Analyze themes button clicked', { allEmailIds: this.allEmailIds });
            const emailIds = this.allEmailIds.filter(id => id && id !== 'N/A' && typeof id === 'string');
            console.log('Filtered email IDs for theme analysis:', emailIds);
            if (emailIds.length === 0) {
                console.warn('No valid email identifiers for theme analysis');
                this.errorMessage.textContent = 'No hay identificadores de correos válidos para analizar.';
                this.errorMessage.style.display = 'block';
                return;
            }
            try {
                console.log('Sending theme analysis request for emails:', emailIds);
                const response = await fetch('/api/analyze_themes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email_ids: emailIds })
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
                if (typeof ThemesModule !== 'undefined') {
                    ThemesModule.renderThemes(data.themes || []);
                } else {
                    console.error('ThemesModule is not defined');
                    this.errorMessage.textContent = 'Error: Módulo de temas no está disponible.';
                    this.errorMessage.style.display = 'block';
                }
            } catch (error) {
                console.error('Error analyzing themes:', error.message);
                this.errorMessage.textContent = `Error al analizar temas: ${error.message}`;
                this.errorMessage.style.display = 'block';
                if (typeof ThemesModule !== 'undefined') {
                    ThemesModule.setCurrentThemes([]);
                }
            }
        });

        // Renderizar filtros iniciales desde sessionStorage
        const initialFilters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        this.renderFilters(initialFilters, this.filterCounts);
    },

    setFilterCounts(counts) {
        console.log('Setting filterCounts:', JSON.stringify(counts, null, 2));
        this.filterCounts = counts || { remove: {}, add: {} };
        if (this.setExternalFilterCounts) {
            this.setExternalFilterCounts(this.filterCounts);
        }
        console.log('Updated filterCounts:', JSON.stringify(this.filterCounts, null, 2));
    },

    showTab() {
        if (!this.searchSection) {
            console.error('consultas-section is undefined, cannot show tab');
            return;
        }
        console.log('Showing Consultas tab');
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.searchSection.classList.add('active');
        this.searchSection.style.display = 'block';
        const tabLink = document.querySelector('.tab-link[data-tab="consultas"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('Tab link for "consultas" not found');
        }
    },

    async performSearch(attempt = 1, maxAttempts = 2) {
        console.log(`Starting performSearch (attempt ${attempt} of ${maxAttempts})`);
        const query = this.queryInput.value.trim();
        const minRelevance = parseInt(this.minRelevanceInput.value) || 10;
        const clearCache = this.clearCacheInput.checked;
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        this.currentQuery = query;
        this.currentMinRelevance = Math.max(0, Math.min(minRelevance, 100));

        if (!query) {
            console.warn('Empty query submitted');
            this.errorMessage.textContent = 'Por favor, introduce una consulta.';
            this.errorMessage.style.display = 'block';
            this.renderFilters(filters, this.filterCounts);
            return;
        }

        this.errorMessage.style.display = 'none';

        if (!sessionStorage.getItem('originalQuery')) {
            sessionStorage.setItem('originalQuery', query);
        } else if (clearCache && query !== sessionStorage.getItem('originalQuery')) {
            sessionStorage.setItem('originalQuery', query);
            sessionStorage.setItem('filters', JSON.stringify([]));
            filters = [];
        }

        try {
            this.resultsBody.innerHTML = '';
            this.resultsTable.style.display = 'none';
            this.noResults.style.display = 'none';
            this.resultsCount.style.display = 'none';
            this.analyzeThemesBtn.style.display = 'none';
            this.showTab();

            console.log('Sending POST request to /api/search', { query, minRelevance: this.currentMinRelevance, page: this.currentPage, clearCache, filters });
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 segundos de tiempo de espera
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    minRelevance: this.currentMinRelevance,
                    page: this.currentPage,
                    resultsPerPage: this.resultsPerPage,
                    clearCache,
                    filters
                }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                if (response.status === 504 && attempt < maxAttempts) {
                    console.warn(`504 Gateway Timeout on attempt ${attempt}, retrying...`);
                    return await this.performSearch(attempt + 1, maxAttempts);
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Search response:', data);
            console.log('Filter counts received:', JSON.stringify(data.filter_counts, null, 2));

            const results = data.results || [];
            const totalResults = data.totalResults || 0;
            const allEmailIds = data.all_email_ids || []; // Almacenar todos los IDs
            this.setFilterCounts(data.filter_counts || { remove: {}, add: {} });
            console.log('Updated filterCounts:', JSON.stringify(this.filterCounts, null, 2));
            const newEmails = results.map(result => ({
                message_id: result.message_id,
                index: result.index
            })).filter(email => (email.message_id && email.message_id !== 'N/A') || (email.index && email.index !== 'N/A'));
            this.currentEmails = newEmails;
            this.allEmailIds = allEmailIds; // Guardar todos los IDs en la variable de estado
            this.setCurrentEmails(newEmails);
            console.log('Updated currentEmails:', this.currentEmails);
            console.log('Updated allEmailIds:', this.allEmailIds);

            if (!Array.isArray(results) || results.length === 0) {
                console.log('No results returned');
                this.noResults.style.display = 'block';
                this.resultsTable.style.display = 'none';
                this.resultsCount.style.display = 'none';
                this.analyzeThemesBtn.style.display = 'none';
            } else {
                this.resultsCount.textContent = `Se encontraron ${totalResults} correos relevantes`;
                this.resultsCount.style.display = 'block';
                this.analyzeThemesBtn.style.display = 'block';
                this.resultsTable.style.display = 'table';
                this.noResults.style.display = 'none';

                results.forEach(result => {
                    console.log('Rendering search result:', { 
                        index: result.index, 
                        message_id: result.message_id, 
                        from: result.from, 
                        to: result.to 
                    });
                    if (!result.message_id && !result.index) {
                        console.warn('Missing message_id and index in result:', result);
                    }
                    const identifier = (result.index && result.index !== 'N/A') ? result.index : result.message_id;
                    const isIndex = (result.index && result.index !== 'N/A');

                    const row = document.createElement('tr');
                    
                    const indexCell = document.createElement('td');
                    const indexLink = document.createElement('a');
                    indexLink.href = '#';
                    indexLink.className = 'index-link';
                    indexLink.dataset.identifier = UtilsModule.escapeHtml(identifier);
                    indexLink.dataset.isIndex = isIndex ? 'true' : 'false';
                    indexLink.textContent = UtilsModule.truncateIndex(identifier);
                    indexCell.appendChild(indexLink);
                    row.appendChild(indexCell);

                    const dateCell = document.createElement('td');
                    dateCell.textContent = UtilsModule.escapeHtml(result.date || '');
                    console.log('Rendered date cell:', dateCell.textContent);
                    row.appendChild(dateCell);

                    const fromCell = document.createElement('td');
                    fromCell.textContent = UtilsModule.escapeHtml(result.from || 'N/A');
                    console.log('Rendered from cell:', fromCell.textContent);
                    row.appendChild(fromCell);

                    const toCell = document.createElement('td');
                    toCell.textContent = UtilsModule.escapeHtml(result.to || 'N/A');
                    console.log('Rendered to cell:', toCell.textContent);
                    row.appendChild(toCell);

                    const subjectCell = document.createElement('td');
                    subjectCell.textContent = UtilsModule.escapeHtml(result.subject || '');
                    console.log('Rendered subject cell:', subjectCell.textContent);
                    row.appendChild(subjectCell);

                    const descCell = document.createElement('td');
                    const descText = (result.summary || '').slice(0, 100);
                    descCell.textContent = UtilsModule.escapeHtml(descText) + (result.summary && result.summary.length > 100 ? '...' : '');
                    console.log('Rendered description cell:', descCell.textContent);
                    row.appendChild(descCell);

                    const termsCell = document.createElement('td');
                    termsCell.textContent = UtilsModule.escapeHtml((result.relevant_terms || []).join(', '));
                    console.log('Rendered terms cell:', termsCell.textContent);
                    row.appendChild(termsCell);

                    const relevanceCell = document.createElement('td');
                    relevanceCell.textContent = result.relevance || '';
                    console.log('Rendered relevance cell:', relevanceCell.textContent);
                    row.appendChild(relevanceCell);

                    const explanationCell = document.createElement('td');
                    explanationCell.textContent = UtilsModule.escapeHtml(result.explanation || '');
                    console.log('Rendered explanation cell:', explanationCell.textContent);
                    row.appendChild(explanationCell);

                    const actionCell = document.createElement('td');
                    const notRelevantBtn = document.createElement('button');
                    notRelevantBtn.className = 'not-relevant';
                    notRelevantBtn.dataset.id = UtilsModule.escapeHtml(result.message_id || result.index || 'N/A');
                    notRelevantBtn.textContent = 'No Relevante';
                    actionCell.appendChild(notRelevantBtn);
                    row.appendChild(actionCell);

                    this.resultsBody.appendChild(row);
                });

                this.resultsBody.querySelectorAll('.index-link').forEach(link => {
                    link.addEventListener('click', (e) => this.showEmailDetails(e));
                });

                this.resultsBody.querySelectorAll('.not-relevant').forEach(button => {
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
                                    query: this.currentQuery,
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
            }

            // Renderizar filtros después de actualizar los resultados
            this.renderFilters(filters, this.filterCounts);
            this.updatePagination(totalResults);
        } catch (err) {
            console.error('Error during search:', err);
            this.errorMessage.textContent = `Error al realizar la búsqueda: ${err.message}`;
            this.errorMessage.style.display = 'block';
            this.resultsTable.style.display = 'none';
            this.noResults.style.display = 'block';
            this.resultsCount.style.display = 'none';
            this.analyzeThemesBtn.style.display = 'none';
            this.renderFilters(filters, this.filterCounts);
            this.updatePagination(0);
        }
    },

    async showEmailDetails(arg) {
        let identifier, isIndex;
        if (arg instanceof Event) {
            arg.preventDefault();
            identifier = arg.target.dataset.identifier;
            isIndex = arg.target.dataset.isIndex === 'true';
        } else {
            identifier = arg;
            isIndex = true;
        }

        if (!identifier || identifier === 'N/A') {
            console.error('No valid identifier provided');
            alert('Identificador de correo no válido.');
            return;
        }

        try {
            console.log('Fetching email details for identifier:', identifier, 'isIndex:', isIndex);
            const response = await fetch(`/api/email?identifier=${encodeURIComponent(identifier)}&is_index=${isIndex}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const email = await response.json();
            console.log('Email details:', email);
            if (!email) {
                console.error('No email data returned for identifier:', identifier);
                alert('No se encontraron detalles para el correo.');
                return;
            }
            const attachmentsContent = Array.isArray(email.attachments_content)
                ? email.attachments_content.join('\n')
                : email.attachments_content || '';

            const detailsDiv = document.getElementById('email-details');
            detailsDiv.innerHTML = '';

            const createField = (label, value, isBody = false) => {
                const p = document.createElement('div');
                p.className = 'email-field';
                const strong = document.createElement('strong');
                strong.textContent = label;
                p.appendChild(strong);
                if (isBody && value) {
                    const bodyDiv = document.createElement('div');
                    bodyDiv.className = 'email-body';
                    // Refinar detección de HTML para evitar falsos positivos
                    const isHTML = /<[a-zA-Z]+(?:\s+[^>]*)*>[\s\S]*<\/[a-zA-Z]+>/i.test(value) && !value.includes('[image:');
                    if (isHTML) {
                        // Sanitizar HTML
                        const tempDiv = document.createElement('div');
                        tempDiv.innerHTML = value;
                        // Eliminar scripts y atributos peligrosos
                        tempDiv.querySelectorAll('script, [on*], iframe, object, embed').forEach(el => el.remove());
                        // Limpiar enlaces con formato [image: ...] <url>
                        const textContent = tempDiv.innerHTML.replace(/\[image:[^\]]+\]\s*(<[^>]+>)/g, '$1');
                        tempDiv.innerHTML = textContent;
                        bodyDiv.appendChild(tempDiv);
                    } else {
                        // Para texto plano, preservar espacios y saltos de línea
                        bodyDiv.style.whiteSpace = 'pre-wrap';
                        // Reemplazar enlaces y hacerlos clicables
                        const formattedValue = value.replace(/\[image:[^\]]+\]\s*<([^>]+)>/g, '<a href="$1" class="email-link dragable">$1</a>');
                        bodyDiv.innerHTML = formattedValue;
                    }
                    p.appendChild(bodyDiv);
                } else {
                    const textNode = document.createTextNode(` ${UtilsModule.escapeHtml(value || 'N/A')}`);
                    p.appendChild(textNode);
                }
                console.log(`Rendered modal field ${label}:`, value);
                detailsDiv.appendChild(p);
            };

            createField('Índice:', email.index);
            createField('ID:', email.message_id);
            createField('De:', email.from);
            createField('Para:', email.to);
            createField('Asunto:', email.subject);
            createField('Fecha:', email.date);
            createField('Resumen:', email.summary);
            createField('Cuerpo:', email.body, true);
            createField('Adjuntos:', attachmentsContent);

            console.log('Rendered modal with from:', email.from, 'to:', email.to);
            document.getElementById('email-modal').style.display = 'flex';
            document.getElementById('not-relevant').dataset.id = email.message_id || email.index;
        } catch (err) {
            console.error('Error fetching email:', err);
            alert('Error al cargar los detalles del correo: ' + err.message);
        }
    },

    updatePagination(totalResults) {
        this.totalPages = Math.ceil(totalResults / this.resultsPerPage) || 1;
        this.setTotalPages(this.totalPages);
        console.log('Total results:', totalResults, 'Total pages:', this.totalPages);

        this.prevPageBtn.disabled = this.currentPage === 1;
        this.nextPageBtn.disabled = this.currentPage >= this.totalPages || totalResults === 0;

        let pageNumbers = '';
        const maxPagesToShow = 10;
        let startPage = Math.max(1, this.currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(this.totalPages, startPage + maxPagesToShow - 1);

        if (endPage - startPage + 1 < maxPagesToShow) {
            startPage = Math.max(1, endPage - maxPagesToShow + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            if (i === this.currentPage) {
                pageNumbers += `<span class="current-page">${i}</span>`;
            } else {
                pageNumbers += `<a href="#" class="page-link" data-page="${i}">${i}</a>`;
            }
        }
        this.pageNumbersSpan.innerHTML = pageNumbers;

        this.pageNumbersSpan.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.currentPage = parseInt(e.target.dataset.page);
                console.log('Navigating to page via link:', this.currentPage);
                this.performSearch();
            });
        });

        this.pagination.style.display = totalResults > 0 ? 'flex' : 'none';
    },

    renderFilters(filters, counts) {
        console.log('Rendering filters:', filters, 'with counts:', JSON.stringify(counts, null, 2));
        if (!this.filtersList) {
            console.error('filtersList element is not found in the DOM');
            this.errorMessage.textContent = 'Error: No se encontró el elemento para mostrar los filtros.';
            this.errorMessage.style.display = 'block';
            return;
        }
        this.filtersList.innerHTML = '';
        if (!Array.isArray(filters) || filters.length === 0) {
            console.log('No filters to render');
            this.filtersList.style.display = 'none';
            console.log('filtersList display set to none');
            return;
        }

        this.filtersList.style.display = 'block';
        console.log('filtersList display set to block');

        filters.forEach((filter, index) => {
            console.log('Creating filter item:', { filter, index });
            const li = document.createElement('li');
            const actionText = filter.action === 'remove' ? 'Eliminar' : 'Añadir';
            const termsText = UtilsModule.escapeHtml(filter.terms.join(', '));
            const termsKey = filter.terms.join(',').toLowerCase();
            console.log('Filter termsKey:', termsKey);
            const count = filter.action === 'remove' ? (counts.remove[termsKey] || 0) : (counts.add[termsKey] || 0);
            console.log('Filter count for', termsText, ':', count);
            const countText = filter.action === 'remove' 
                ? `(<a href="#" class="filter-count-link" data-index="${index}">${count} correo${count !== 1 ? 's' : ''} eliminado${count !== 1 ? 's' : ''}</a>)`
                : `(<a href="#" class="filter-count-link" data-index="${index}">${count} correo${count !== 1 ? 's' : ''} añadido${count !== 1 ? 's' : ''}</a>)`;
            li.innerHTML = `${actionText}: ${termsText} ${countText}`;

            const removeBtn = document.createElement('button');
            removeBtn.textContent = 'X';
            removeBtn.className = 'remove-filter';
            removeBtn.onclick = () => this.removeFilter(index);
            li.appendChild(removeBtn);

            const notRelevantBtn = document.createElement('button');
            notRelevantBtn.textContent = 'Marcar como No Relevantes';
            notRelevantBtn.className = 'not-relevant-filter';
            notRelevantBtn.onclick = () => this.markFilterAsNotRelevant(filter, index);
            li.appendChild(notRelevantBtn);

            this.filtersList.appendChild(li);

            li.querySelector('.filter-count-link').addEventListener('click', (e) => {
                e.preventDefault();
                console.log('Filter count link clicked:', { filter, index });
                this.showFilterEmailsModal(filter);
            });
        });
        console.log('Filters rendered, filtersList content:', this.filtersList.innerHTML);
        console.log('filtersList display style after rendering:', this.filtersList.style.display);
        console.log('filtersList computed style:', window.getComputedStyle(this.filtersList).display);
    },

    removeFilter(index) {
        console.log('Removing filter at index:', index);
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        filters.splice(index, 1);
        sessionStorage.setItem('filters', JSON.stringify(filters));
        this.renderFilters(filters, this.filterCounts);
        this.performSearch();
    },

    async markFilterAsNotRelevant(filter, index) {
        console.log('Marking emails for filter as not relevant:', filter);
        try {
            const response = await fetch('/api/bulk_feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: this.currentQuery,
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
            this.performSearch();
        } catch (err) {
            console.error('Error sending bulk feedback:', err);
            alert('Error al marcar correos como no relevantes: ' + err.message);
        }
    },

    async showFilterEmailsModal(filter) {
        console.log('Fetching emails for filter:', filter);
        try {
            const response = await fetch('/api/filter_emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: this.currentQuery,
                    filter: filter,
                    user: 'andres.marchante'
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
                from: email.from,
                to: email.to,
                relevant_terms: email.relevant_terms || [],
                description: email.description
            })));

            const filterModal = document.createElement('div');
            filterModal.className = 'modal';
            filterModal.style.display = 'flex';
            filterModal.innerHTML = `
                <div class="modal-content">
                    <span class="close">×</span>
                    <h2>Correos ${filter.action === 'remove' ? 'Eliminados' : 'Añadidos'} por el Filtro: ${UtilsModule.escapeHtml(filter.terms.join(', '))}</h2>
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
                                ${data.results.map(email => {
                                    const identifier = email.message_id && email.message_id !== 'N/A' ? email.message_id : email.index;
                                    const isIndex = email.index && email.index !== 'N/A';
                                    const displayText = isIndex ? UtilsModule.truncateIndex(identifier) : (identifier.slice(0, 11) + '...');
                                    console.log(`Email identifier: ${identifier}, isIndex: ${isIndex}, displayText: ${displayText}`);
                                    return `
                                        <tr>
                                            <td><a href="#" class="index-link" data-identifier="${UtilsModule.escapeHtml(identifier)}" data-is-index="${isIndex}">${UtilsModule.escapeHtml(displayText)}</a></td>
                                            <td>${UtilsModule.escapeHtml(new Date(email.date).toLocaleString())}</td>
                                            <td>${UtilsModule.escapeHtml(email.subject)}</td>
                                            <td>${UtilsModule.escapeHtml(email.from)}</td>
                                            <td>${UtilsModule.escapeHtml(email.to)}</td>
                                            <td>${UtilsModule.escapeHtml(email.description)}</td>
                                        </tr>
                                    `;
                                }).join('')}
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

            filterModal.querySelectorAll('.index-link').forEach(link => {
                link.addEventListener('click', (e) => this.showEmailDetails(e));
            });
        } catch (error) {
            console.error('Error fetching filter emails:', error);
            alert('Error al cargar los correos del filtro: ' + error.message);
        }
    }
};