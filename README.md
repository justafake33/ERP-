# SilkManager (uso interno de estamparia)

Sistema web simples para centralizar **pedidos, produção, CRM, orçamentos, financeiro, dashboard e relatórios**.

## Como executar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python monitor.py
```

Acesse: `http://localhost:5000`

## Módulos implementados

- Dashboard com KPIs (faturamento do mês, produção, entregues, atrasados)
- Pedidos com filtros e histórico
- Produção do dia (em produção, prazo hoje, atrasados)
- Orçamentos com conversão para pedido
- CRM de clientes com valor total comprado e último pedido
- Financeiro (entradas, saídas e saldo)
- Relatórios por API (produção, financeiro, pedidos por cliente, faturamento por período)

## APIs principais

- `GET/POST /api/clients`
- `GET/POST /api/quotes`
- `POST /api/quotes/<id>/convert`
- `GET/POST /api/orders`
- `GET/PATCH /api/orders/<id>`
- `GET /api/production/today`
- `GET/POST /api/financial`
- `GET /api/dashboard`
- `GET /api/reports?type=production|financial|orders_by_client|revenue_period`

## Observações

- Banco local: `sqlite` em `silk_manager.db`.
- Uploads de artes/anexos: pasta `uploads/`.
- O sistema faz carga inicial com dados de exemplo no primeiro start.

## Opção mais simples (sem instalar nada)

Se você é iniciante, use o arquivo **`silkmanager_offline.html`**:

1. Baixe o arquivo para seu computador.
2. Dê duplo clique nele (abre no navegador).
3. Use normalmente; os dados ficam salvos no navegador (`localStorage`).
4. Use os botões de **Exportar/Importar backup** para guardar/restaurar dados.

> Nessa opção você **não precisa Google Colab**.
