const byId = (id) => document.getElementById(id);
const labels = { connected: 'Conectado', disconnected: 'Sin conexión', not_configured: 'No configurado en desarrollo' };

async function updateStatus() {
  try {
    const response = await fetch('/status', { signal: AbortSignal.timeout(10000) });
    const data = await response.json();
    for (const service of ['database', 'cache']) {
      byId(service).textContent = labels[data.services[service]];
      byId(service).className = data.services[service];
    }
    byId('status-message').textContent = data.status === 'healthy'
      ? 'Todos los servicios necesarios responden.' : 'Hay un servicio que no responde.';
  } catch {
    byId('status-message').textContent = 'No se puede consultar la aplicación.';
    for (const service of ['database', 'cache']) {
      byId(service).textContent = 'Estado desconocido';
      byId(service).className = 'disconnected';
    }
  } finally {
    setTimeout(updateStatus, 5000);
  }
}

async function loadNotes() {
  byId('refresh').disabled = true;
  try {
    const response = await fetch('/api/notes', { signal: AbortSignal.timeout(10000) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pueden consultar las notas.');
    const states = { hit: 'acierto de caché; no se ha consultado PostgreSQL para esta lista',
      miss: 'copia temporal creada en Redis', disabled: 'caché desactivada', unavailable: 'caché no disponible' };
    byId('source').textContent = `Origen: ${data.source} · ${states[data.cache]}`;
    byId('notes').replaceChildren();
    for (const note of data.notes) {
      const li = document.createElement('li');
      const text = document.createElement('p');
      text.textContent = note.content;
      const time = document.createElement('small');
      time.textContent = `#${note.id} · ${new Date(note.created_at).toLocaleString('es-ES')}`;
      li.append(text, time);
      byId('notes').append(li);
    }
    if (data.notes.length === 0) byId('notes').textContent = 'Todavía no hay notas. Crea la primera.';
  } catch (error) {
    byId('source').textContent = error.message;
    byId('notes').replaceChildren();
  } finally {
    byId('refresh').disabled = false;
  }
}

byId('note-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/notes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: byId('content').value }),
      signal: AbortSignal.timeout(10000),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se ha podido guardar.');
    byId('content').value = '';
    byId('form-message').textContent = data.warning || `Nota #${data.note.id} guardada.`;
    await loadNotes();
  } catch (error) {
    byId('form-message').textContent = `${error.message} Consulta las notas antes de reintentar si hubo un corte de conexión.`;
  } finally {
    button.disabled = false;
  }
});
byId('refresh').addEventListener('click', loadNotes);
updateStatus();
loadNotes();
