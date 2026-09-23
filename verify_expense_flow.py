from app import app, init_db
import os

if os.path.exists('solobiz.db'):
    os.remove('solobiz.db')

init_db()
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 'user-123'

    add = client.post('/add', json={
        'amount': 150.5,
        'category': 'Fuel & Electricity',
        'description': 'Generator fuel'
    })
    print('ADD', add.status_code, add.get_json())
    expense_id = add.get_json()['expense']['id']

    upd = client.put(f'/api/expenses/{expense_id}', json={
        'amount': 199.99,
        'category': 'Others',
        'description': 'Updated fuel'
    })
    print('PUT', upd.status_code, upd.get_json())

    delr = client.post(f'/delete/{expense_id}')
    print('DELETE_WEB', delr.status_code, delr.location)

    getr = client.get('/api/expenses')
    print('GET_API', getr.status_code, getr.get_json())
