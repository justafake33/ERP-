const titleEl = document.getElementById('module-title');
const modules = document.querySelectorAll('.module');

document.querySelectorAll('.sidebar button').forEach((button) => {
  button.addEventListener('click', async () => {
    const module = button.dataset.module;
    titleEl.textContent = button.textContent;
    modules.forEach((el) => el.classList.remove('active'));
    document.getElementById(module).classList.add('active');
    await renderModule(module);
  });
});

function card(label, value) {
  return `<div class="card"><small>${label}</small><strong>${value}</strong></div>`;
}

async function renderDashboard() {
  const data = await fetch('/api/dashboard').then((r) => r.json());
  const k = data.kpis;
  document.getElementById('dashboard').innerHTML = `
    <div class="grid four">
      ${card('Faturamento do mês', `R$ ${Number(k.monthly_revenue || 0).toFixed(2)}`)}
      ${card('Pedidos em produção', k.in_production || 0)}
      ${card('Pedidos entregues', k.delivered || 0)}
      ${card('Pedidos atrasados', k.delayed || 0)}
    </div>
    <div class="table-block">
      <h3>Clientes que mais compram</h3>
      <table>
        <thead><tr><th>Cliente</th><th>Total (R$)</th></tr></thead>
        <tbody>
          ${data.top_clients.map(c => `<tr><td>${c.name}</td><td>${Number(c.total).toFixed(2)}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

async function renderOrders() {
  const orders = await fetch('/api/orders').then((r) => r.json());
  document.getElementById('orders').innerHTML = `
    <div class="table-block">
      <h3>Histórico de Pedidos</h3>
      <table>
        <thead><tr><th>Cliente</th><th>Produto</th><th>Qtd</th><th>Status</th><th>Cores</th><th>Prazo</th><th>Preço</th></tr></thead>
        <tbody>
          ${orders.map(o => `<tr><td>${o.client_name}</td><td>${o.product_type}</td><td>${o.total_quantity}</td><td>${o.status}</td><td>${o.colors_count}</td><td>${o.due_date}</td><td>R$ ${Number(o.price).toFixed(2)}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

async function renderProduction() {
  const data = await fetch('/api/production/today').then((r) => r.json());
  const renderList = (items) => items.map((o) => `
      <li>
        <strong>${o.client_name}</strong> - ${o.product_type}<br />
        Qtd: ${o.total_quantity} | Cores: ${o.colors_count} | Prazo: ${o.due_date}<br />
        <em>${o.notes || 'Sem observações'}</em>
      </li>`).join('');

  document.getElementById('production').innerHTML = `
    <div class="grid three">
      <div class="table-block"><h3>Em produção</h3><ul>${renderList(data.in_production)}</ul></div>
      <div class="table-block"><h3>Prazo hoje</h3><ul>${renderList(data.due_today)}</ul></div>
      <div class="table-block"><h3>Atrasados</h3><ul>${renderList(data.delayed)}</ul></div>
    </div>
  `;
}

async function renderQuotes() {
  const quotes = await fetch('/api/quotes').then((r) => r.json());
  document.getElementById('quotes').innerHTML = `
    <div class="table-block">
      <h3>Histórico de Orçamentos</h3>
      <table>
        <thead><tr><th>Cliente</th><th>Produto</th><th>Qtd</th><th>Cores</th><th>Valor</th><th>Status</th></tr></thead>
        <tbody>
          ${quotes.map(q => `<tr><td>${q.client_name}</td><td>${q.product_type}</td><td>${q.quantity}</td><td>${q.colors_count}</td><td>R$ ${Number(q.value).toFixed(2)}</td><td>${q.status}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

async function renderClients() {
  const clients = await fetch('/api/clients').then((r) => r.json());
  document.getElementById('clients').innerHTML = `
    <div class="table-block">
      <h3>CRM de Clientes</h3>
      <table>
        <thead><tr><th>Nome</th><th>Empresa</th><th>Telefone</th><th>Total pedidos</th><th>Valor comprado</th><th>Último pedido</th></tr></thead>
        <tbody>
          ${clients.map(c => `<tr><td>${c.name}</td><td>${c.company || '-'}</td><td>${c.phone || '-'}</td><td>${c.total_orders}</td><td>R$ ${Number(c.total_purchased).toFixed(2)}</td><td>${c.last_order_date || '-'}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

async function renderFinancial() {
  const data = await fetch('/api/financial').then((r) => r.json());
  document.getElementById('financial').innerHTML = `
    <div class="grid three">
      ${card('Entradas', `R$ ${Number(data.summary.total_entries).toFixed(2)}`)}
      ${card('Saídas', `R$ ${Number(data.summary.total_expenses).toFixed(2)}`)}
      ${card('Saldo', `R$ ${Number(data.summary.balance).toFixed(2)}`)}
    </div>
    <div class="table-block">
      <h3>Lançamentos</h3>
      <table>
        <thead><tr><th>Tipo</th><th>Cliente/Fornecedor</th><th>Categoria</th><th>Data</th><th>Valor</th></tr></thead>
        <tbody>
          ${data.entries.map(e => `<tr><td>${e.kind}</td><td>${e.client_or_vendor || '-'}</td><td>${e.category || '-'}</td><td>${e.entry_date}</td><td>R$ ${Number(e.value).toFixed(2)}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

async function renderReports() {
  const [production, financial] = await Promise.all([
    fetch('/api/reports?type=production').then(r => r.json()),
    fetch('/api/reports?type=financial').then(r => r.json())
  ]);

  document.getElementById('reports').innerHTML = `
    <div class="grid two">
      <div class="table-block"><h3>Relatório de Produção</h3><p>Total de linhas: ${production.data.length}</p></div>
      <div class="table-block"><h3>Relatório Financeiro</h3><p>Total de linhas: ${financial.data.length}</p></div>
    </div>
    <p>Use as APIs para extrair relatórios completos por período, cliente e histórico.</p>
  `;
}

async function renderModule(module) {
  if (module === 'dashboard') return renderDashboard();
  if (module === 'orders') return renderOrders();
  if (module === 'production') return renderProduction();
  if (module === 'quotes') return renderQuotes();
  if (module === 'clients') return renderClients();
  if (module === 'financial') return renderFinancial();
  if (module === 'reports') return renderReports();
}

renderModule('dashboard');
