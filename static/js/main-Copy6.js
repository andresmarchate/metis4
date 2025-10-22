document.addEventListener('DOMContentLoaded', () => {
    console.log('main.js loaded successfully');

    // Select DOM elements
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const minRelevanceInput = document.getElementById('min-relevance');
    const resultsTable = document.getElementById('results-table');
    const resultsBody = document.getElementById('results-body');
    const noResults = document.getElementById('no-results');
    const pagination = document.getElementById('pagination');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const pageNumbersSpan = document.getElementById('page-numbers');
    const modal = document.getElementById('email-modal');
    const modalContent = document.getElementById('email-details');
    const closeModal = document.querySelector('.close');
    const notRelevantBtn = document.getElementById('not-relevant');

    let currentQuery = '';
    let currentMinRelevance = 10; // Valor por defecto
    let currentPage = 1;
    let totalPages = 1;
    const resultsPerPage = 25;

    // Verify form exists
    if (!form) {
        console.error('Search form not found in DOM');
        return;
    }

    // Escape HTML characters to prevent rendering issues
    function escapeHtml(unsafe) {
        if (!unsafe) return 'N/A';
        // Convert to string if not already (handles arrays, objects, etc.)
        let safe = typeof unsafe === 'string' ? unsafe : String(unsafe);
        return safe
            .replace(/&/g, "&")
            .replace(/</g, "&lt;")  // Escape < to prevent HTML tag interpretation
            .replace(/>/g, "&gt;")  // Escape > to prevent HTML tag interpretation
            .replace(/"/g, "\"")
            .replace(/'/g, "'");
    }

    // Format email address (backend provides "Name <email>" or "<email>")
    function formatEmail(field) {
        if (!field) return 'N/A';
        // Ensure field is a string
        field = field.toString();
        // Backend should already format as "Name <email>" or "<email>"
        // Only handle edge cases (e.g., plain email not wrapped in < >)
        if (!field.match(/<[^>]+>/) && field.includes('@')) {
            return `<${field}>`;
        }
        return field;
    }

    // Update pagination controls
    function updatePagination(totalResults) {
        totalPages = Math.ceil(totalResults / resultsPerPage);
        console.log('Total results:', totalResults, 'Total pages:', totalPages);

        // Update buttons
        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages || totalPages === 0;

        // Generate page numbers (similar to Google: show up to 10 pages around the current page)
        let pageNumbers = '';
        const maxPagesToShow = 10;
        let startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

        // Adjust startPage if endPage is at the maximum
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

        // Add event listeners to page links
        document.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                currentPage = parseInt(e.target.dataset.page);
                performSearch();
            });
        });

        // Show pagination controls if there are results
        pagination.style.display = totalResults > 0 ? 'block' : 'none';
    }

    // Perform search with pagination
    async function performSearch() {
        const query = queryInput.value.trim();
        const minRelevance = parseInt(minRelevanceInput.value) || 10;
        currentQuery = query;
        currentMinRelevance = Math.max(0, Math.min(minRelevance, 100)); // Limit between 0 and 100

        if (!query) {
            console.warn('Empty query submitted');
            alert('Por favor, introduce una consulta.');
            return;
        }

        try {
            // Clear previous results
            resultsBody.innerHTML = '';
            resultsTable.style.display = 'none';
            noResults.style.display = 'none';

            console.log('Sending POST request to /api/search', { query, minRelevance: currentMinRelevance, page: currentPage });
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    minRelevance: currentMinRelevance,
                    page: currentPage,
                    resultsPerPage
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

            if (!Array.isArray(results) || results.length === 0) {
                console.log('No results returned');
                noResults.style.display = 'block';
                updatePagination(0);
                return;
            }

            resultsTable.style.display = 'table';
            results.forEach(result => {
                console.log('Processing result:', result);
                if (!result.message_id) {
                    console.warn('Missing message_id in result:', result);
                }
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><a href="#" class="index-link" data-id="${escapeHtml(result.message_id || '')}">${result.index || ''}</a></td>
                    <td>${escapeHtml(result.date || '')}</td>
                    <td>${escapeHtml(formatEmail(result.from))}</td>
                    <td>${escapeHtml(formatEmail(result.to))}</td>
                    <td>${escapeHtml(result.subject || '')}</td>
                    <td>${escapeHtml((result.description || '').slice(0, 50))}${result.description && result.description.length > 50 ? '...' : ''}</td>
                    <td>${escapeHtml((result.relevant_terms || []).join(', '))}</td>
                    <td>${result.relevance || ''}</td>
                    <td>${escapeHtml(result.explanation || '')}</td>
                    <td><button class="not-relevant" data-id="${escapeHtml(result.message_id || '')}">No Relevante</button></td>
                `;
                resultsBody.appendChild(row);
            });

            // Update pagination
            updatePagination(totalResults);

            // Add event listeners for index links
            const indexLinks = document.querySelectorAll('.index-link');
            console.log('Found index links:', indexLinks.length);
            indexLinks.forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const messageId = e.target.dataset.id;
                    console.log('Clicked index link with message_id:', messageId);
                    if (!messageId) {
                        console.error('No message_id found for link:', e.target);
                        alert('ID de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Fetching email details for:', messageId);
                        const response = await fetch(`/api/email/${encodeURIComponent(messageId)}`);
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const email = await response.json();
                        console.log('Email details:', email);
                        console.log('Rendering message_id in modal:', email.message_id);
                        console.log('Rendering from in modal:', email.from);
                        console.log('Rendering to in modal:', email.to);
                        // Handle attachments_content as an array
                        const attachmentsContent = Array.isArray(email.attachments_content)
                            ? email.attachments_content.join('\n')
                            : email.attachments_content || 'N/A';
                        modalContent.innerHTML = `
                            <p><strong>ID:</strong> ${escapeHtml(email.message_id || 'N/A')}</p>
                            <p><strong>De:</strong> ${escapeHtml(formatEmail(email.from))}</p>
                            <p><strong>Para:</strong> ${escapeHtml(formatEmail(email.to))}</p>
                            <p><strong>Asunto:</strong> ${escapeHtml(email.subject || 'N/A')}</p>
                            <p><strong>Fecha:</strong> ${escapeHtml(email.date || 'N/A')}</p>
                            <p><strong>Resumen:</strong> ${escapeHtml(email.summary || 'N/A')}</p>
                            <p><strong>Cuerpo:</strong> ${escapeHtml(email.body || 'N/A')}</p>
                            <p><strong>Adjuntos:</strong> ${escapeHtml(attachmentsContent)}</p>
                        `;
                        modal.style.display = 'block';
                        notRelevantBtn.dataset.id = messageId;
                    } catch (error) {
                        console.error('Error fetching email:', error);
                        alert('Error al cargar los detalles del correo: ' + error.message);
                    }
                });
            });

            // Add event listeners for "No Relevante" buttons
            document.querySelectorAll('.not-relevant').forEach(button => {
                button.addEventListener('click', async () => {
                    const messageId = button.dataset.id;
                    console.log('Marking email as not relevant (table):', messageId);
                    if (!messageId) {
                        console.error('No message_id for feedback button');
                        alert('ID de correo no válido.');
                        return;
                    }
                    try {
                        const response = await fetch('/api/feedback', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                query: currentQuery,
                                message_id: messageId,
                                is_relevant: false
                            })
                        });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        console.log('Feedback sent successfully');
                        alert('Retroalimentación enviada.');
                    } catch (error) {
                        console.error('Error sending feedback:', error);
                        alert('Error al enviar retroalimentación: ' + error.message);
                    }
                });
            });
        } catch (error) {
            console.error('Error during search:', error);
            noResults.style.display = 'block';
            noResults.textContent = 'Error al realizar la búsqueda: ' + error.message;
            updatePagination(0);
        }
    }

    // Pagination button event listeners
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

    // Form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        currentPage = 1; // Reset to first page on new search
        performSearch();
    });

    // Close modal
    if (closeModal) {
        closeModal.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    // Close modal when clicking outside
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });

    // Handle "No Relevante" in modal
    if (notRelevantBtn) {
        notRelevantBtn.addEventListener('click', async () => {
            const messageId = notRelevantBtn.dataset.id;
            console.log('Marking email as not relevant from modal:', messageId);
            if (!messageId) {
                console.error('No message_id for modal feedback');
                alert('ID de correo no válido.');
                return;
            }
            try {
                const response = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: currentQuery,
                        message_id: messageId,
                        is_relevant: false
                    })
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                console.log('Feedback sent successfully');
                alert('Retroalimentación enviada.');
                modal.style.display = 'none';
            } catch (error) {
                console.error('Error sending feedback:', error);
                alert('Error al enviar retroalimentación: ' + error.message);
            }
        });
    }
});