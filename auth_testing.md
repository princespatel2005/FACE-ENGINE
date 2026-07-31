# Auth Testing Playbook

## Admin credentials
- email: `admin@example.com`
- password: `admin123`

## Verify DB
```
mongosh
use $DB_NAME
db.users.find({role:"admin"}).pretty()
```
Password hash must start with `$2b$`. Indexes: `users.email` unique, `login_attempts.identifier`.

## API
```
API=$REACT_APP_BACKEND_URL
curl -c /tmp/c.txt -X POST $API/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"admin123"}'
curl -b /tmp/c.txt $API/api/auth/me
```
