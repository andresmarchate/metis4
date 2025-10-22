document.addEventListener('DOMContentLoaded', () => {
    console.log('main.js loaded successfully');

    // Select DOM elements
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const resultsTable = document.getElementById('results-table');
    const resultsBody = document.getElementById('results-body');
    const noResults = document.getElementById('no-results');
    const modal = document.getElementById('email-modal');
    const modalContent = document.getElementById('email-details');
    const closeModal = document.querySelector('.close');
    const notRelevantBtn = document.getElementById('not-relevant');

    let currentQuery = '';

    // Verify form exists
    if (!form) {
        console.error('Search form not found in DOM');
        return;
    }

    // Handle form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        console.log('Submitting query:', query);
        currentQuery = query;

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

            console.log('Sending POST request to /api/search');
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });

            console.log('Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const results = await response.json();
            console.log('Search results:', results);

            if (!Array.isArray(results) || results.length === 0) {
                console.log('No results returned');
                noResults.style.display = 'block';
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
                    <td><a href="#" class="index-link" data-id="${result.message_id || ''}">${result.index || ''}</a></td>
                    <td>${result.message_id ? result.message_id.slice(0, 8) + '...' : 'N/A'}</td>
                    <td>${result.date || ''}</td>
                    <td>${result.from || ''}</td>
                    <td>${result.to || ''}</td>
                    <td>${result.subject || ''}</td>
                    <td>${(result.description || '').slice(0, 50)}${result.description && result.description.length > 50 ? '...' : ''}</td>
                    <td>${(result.relevant_terms || []).join(', ')}</td>
                    <td>${result.relevance || ''}</td>
                    <td>${result.explanation || ''}</td>
                    <td><button class="not-relevant" data-id="${result.message_id || ''}">No Relevante</button></td>
                `;
                resultsBody.appendChild(row);
            });

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
                        modalContent.innerHTML = `
                            <p><strong>De:</strong> ${email.from || 'N/A'}</p>
                            <p><strong>Para:</strong> ${email.to || 'N/A'}</p>
                            <p><strong>Asunto:</strong> ${email.subject || 'N/A'}</p>
                            <p><strong>Fecha:</strong> ${email.date || 'N/A'}</p>
                            <p><strong>Cuerpo:</strong> ${email.body || 'N/A'}</p>
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
                    console.log('Marking email as not relevant:', messageId);
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
        }
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