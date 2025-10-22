/* Artifact ID: a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890 */
/* Version: a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890 */
const UtilsModule = {
    normalizeText(text) {
        if (!text || typeof text !== 'string') return text;
        return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    },

    escapeHtml(unsafe, isMessageId = false) {
        if (!unsafe || unsafe === 'Unknown') return 'N/A';
        let safe = typeof unsafe === 'string' ? unsafe : String(unsafe);
        console.log('Escaping HTML:', { unsafe, isMessageId });

        if (isMessageId || safe.match(/(?:^[^<]+<[^>]+@[^>]+>$|^<[^>]+@[^>]+>$|^[^<>\s]+@[^<>\s]+$)/)) {
            console.log('Preserving email format:', safe);
            return safe.replace(/</g, '<').replace(/>/g, '>');
        }

        console.log('Escaping non-email text:', safe);
        return safe
            .replace(/&/g, '&')
            .replace(/</g, '<')
            .replace(/>/g, '>')
            .replace(/"/g, '"')
            .replace(/'/g, '');
    },

    truncateIndex(index) {
        return index && index !== 'N/A' ? index.slice(0, 8) + '...' : 'N/A';
    },

    parseFilterPrompt(prompt) {
        if (!prompt || typeof prompt !== 'string') return null;
        const normalizedPrompt = this.normalizeText(prompt.trim());
        const removeMatch = normalizedPrompt.match(/^(elimina|excluye|remove|delete)\s+correos\s+que\s+incluyan\s*(.+)/i);
        const addMatch = normalizedPrompt.match(/^(anade|añade|agrega|incluye|add|include)\s+correos\s+que\s*incluyan\s*(.+)/i);

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
};