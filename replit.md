# Overview

This is a comprehensive Hotel Sales Request Management System built with Django, designed to streamline hotel sales operations. The system manages client accounts, booking requests, yearly agreements, and sales calls through a centralized web platform. It supports various accommodation types from individual bookings to large group events, with detailed tracking of financial metrics, deadlines, and business relationships.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Framework
The system uses Django as the primary backend framework with a traditional Model-View-Controller architecture. The project is structured into four main Django apps:

- **accounts**: Manages client companies, governments, and travel agencies
- **requests**: Handles accommodation and event requests with complex room configurations
- **agreements**: Tracks yearly contracts and rate agreements with deadline monitoring
- **sales_calls**: Records business meetings and follow-up activities
- **dashboard**: Provides analytics and overview functionality

## Database Design
The system uses Django's ORM with SQLite as the default database (easily configurable for PostgreSQL or other databases). Key architectural decisions include:

- **Normalized relationships**: Foreign keys connect accounts to requests, agreements, and sales calls
- **Unique constraints**: Prevent duplicate accounts (name + type combination) and agreements
- **Auto-calculated fields**: Financial totals, room nights, and date calculations are handled automatically
- **Signal-based updates**: Django signals ensure data consistency when related objects change

## Request Management Architecture
The requests module supports complex booking scenarios through a flexible model design:

- **Polymorphic request types**: Single model handles group accommodation, individual bookings, events, and series groups
- **Inline relationships**: Room entries, transportation, event agendas, and series data are managed as related objects
- **Real-time calculations**: Total costs, room nights, and occupancy metrics update automatically
- **Status workflow**: Tracks requests from draft through confirmation, payment, and potential cancellation

## Financial Tracking
The system implements comprehensive financial monitoring:

- **Automatic totals**: Room costs and transportation expenses calculate total request value
- **Payment tracking**: Monitors deposits, partial payments, and outstanding balances
- **Revenue analytics**: Dashboard provides paid vs. unpaid breakdowns and lost revenue from cancellations
- **Deadline management**: Payment and agreement deadlines with alert systems

## File Management
Django's file handling system manages document uploads:

- **Agreement storage**: Signed contracts and rate agreements stored in organized directories
- **Media configuration**: Separate media root for development and production environments

## Admin Interface
Heavily customized Django admin provides the primary user interface:

- **Inline editing**: Related objects (rooms, transportation, agendas) editable within parent records
- **Smart filtering**: Date ranges, status filters, and search functionality across all modules
- **Visual indicators**: Color-coded status displays for deadlines and follow-ups
- **Bulk operations**: Efficient management of multiple records

## Dashboard and Analytics
The dashboard module aggregates data across all apps:

- **Key metrics**: Account totals, request statistics, revenue tracking
- **Visual charts**: Request type breakdowns and status distributions (prepared for Chart.js integration)
- **Recent activity**: Timeline of latest requests and sales calls
- **Alert system**: Approaching deadlines and overdue items

# External Dependencies

## Core Framework
- **Django 5.2.6**: Primary web framework providing ORM, admin interface, and routing
- **Python 3**: Backend programming language with extensive library ecosystem

## Frontend Libraries
- **Bootstrap 5.3.0**: CSS framework for responsive design and UI components
- **Font Awesome 6.0.0**: Icon library for improved user interface
- **Chart.js**: JavaScript charting library for dashboard analytics (referenced in API endpoints)

## Development Environment
- **Replit compatibility**: CSRF trusted origins configured for Replit hosting
- **SQLite database**: Default database for development (production-ready for PostgreSQL migration)
- **Django's development server**: Built-in server for development and testing

## File Storage
- **Local file system**: Media files stored in project directory structure
- **Django's FileField**: Handles agreement and contract uploads with organized directory structure

## Potential Integrations
The architecture supports future integration with:
- **Email systems**: For automated deadline notifications and agreement distribution
- **Payment processors**: For direct payment tracking and processing
- **Calendar systems**: For event scheduling and meeting management
- **Export functionality**: CSV/Excel export capabilities for data analysis