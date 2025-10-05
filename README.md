# Hotel Sales Management System

A comprehensive Django-based hotel sales management system with support for both local development and production deployment.

## Features

- **Account Management**: Manage travel agencies, government entities, companies, and other business segments
- **Request Management**: Handle accommodation, event, and series group requests
- **Agreement Management**: Track contracts and agreements
- **Sales Call Tracking**: Monitor sales activities and follow-ups
- **Dashboard Analytics**: Real-time insights and reporting
- **Multi-Currency Support**: SAR and USD with automatic conversion
- **Dynamic Configuration**: Flexible field management system

## Local Development Setup

### Prerequisites
- Python 3.11+
- pip (Python package installer)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Xas-21/Hotel-Sales.git
   cd Hotel-Sales
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations**
   ```bash
   python manage.py migrate
   ```

5. **Create superuser**
   ```bash
   python manage.py createsuperuser
   # Username: Abdullah
   # Email: admin@example.com
   # Password: Welcome@2025
   ```

6. **Start development server**
   ```bash
   python manage.py runserver
   ```

7. **Access the application**
   - Main application: http://127.0.0.1:8000/
   - Admin panel: http://127.0.0.1:8000/admin/
   - Dashboard: http://127.0.0.1:8000/dashboard/

### Local Database
- Uses SQLite (`db.sqlite3`) for local development
- Database file is automatically created and excluded from Git
- No additional database setup required

## Production Deployment

### Environment Variables
The application uses the following environment variables in production:

```bash
DATABASE_URL=postgresql://postgres:PASSWORD@db.uwvqtpcealodvfhokfvn.supabase.co:5432/postgres
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.onrender.com
```

### Render Deployment
1. Connect GitHub repository to Render
2. Set environment variables in Render dashboard
3. Deploy automatically from GitHub

### Supabase Database
- Production uses Supabase PostgreSQL
- Migrations run automatically on deployment
- Data persists across deployments

## Development Workflow

### Making Changes
1. Make code changes locally
2. Test with local SQLite database
3. Commit and push to GitHub
4. Render automatically deploys from GitHub

### Database Management
- **Local**: SQLite database (`db.sqlite3`)
- **Production**: Supabase PostgreSQL
- Migrations: `python manage.py migrate`
- Superuser creation: `python manage.py createsuperuser`

## System Architecture

### Django Apps
- `accounts`: Account and user management
- `dashboard`: Main dashboard and analytics
- `requests`: Request management system
- `agreements`: Contract and agreement tracking
- `sales_calls`: Sales activity management

### Key Features
- **Dynamic Configuration**: Flexible field management
- **Multi-Currency**: SAR/USD support with conversion
- **Export Functions**: CSV export with comprehensive summaries
- **Notification System**: Deadline and alert management
- **Responsive Design**: Works on desktop and mobile

## Troubleshooting

### Common Issues
1. **Database connection errors**: Check environment variables
2. **Static files not loading**: Run `python manage.py collectstatic`
3. **Migration errors**: Check database permissions and connection

### Support
For technical support or questions, please contact the development team.

## License
This project is proprietary software. All rights reserved.
