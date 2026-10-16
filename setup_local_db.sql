/* ------------------------------------------------------------------
   App Directory Bot - local database setup (SQL Server 2025, localhost)
   Creates DevDB + dbo.Applications, dbo.FAQs, dbo.QueryLog with sample data.
   Safe to re-run: tables are dropped and recreated.

   Run:  sqlcmd -S localhost -E -C -i setup_local_db.sql
     or: open in SSMS 22 (localhost, Windows Auth) and press F5.

   Sample rows are placeholders - replace URLs/contacts with real ones,
   or load your real data from Azure SQL into these tables.
------------------------------------------------------------------- */
IF DB_ID(N'DevDB') IS NULL
    CREATE DATABASE DevDB;
GO
USE DevDB;
GO

DROP TABLE IF EXISTS dbo.QueryLog;
DROP TABLE IF EXISTS dbo.FAQs;
DROP TABLE IF EXISTS dbo.Applications;
GO

CREATE TABLE dbo.Applications (
    app_id            NVARCHAR(20)   NOT NULL PRIMARY KEY,
    app_name          NVARCHAR(200)  NOT NULL,
    category          NVARCHAR(100)  NULL,
    short_description NVARCHAR(1000) NULL,
    url               NVARCHAR(500)  NOT NULL,
    keywords          NVARCHAR(1000) NULL,   -- comma-separated
    access_notes      NVARCHAR(500)  NULL,
    owner_contact     NVARCHAR(200)  NULL,
    status            NVARCHAR(20)   NOT NULL DEFAULT N'Active'  -- bot reads only 'Active'
);

CREATE TABLE dbo.FAQs (
    faq_id         NVARCHAR(20)   NOT NULL PRIMARY KEY,
    question       NVARCHAR(500)  NOT NULL,
    answer         NVARCHAR(2000) NOT NULL,
    related_app_id NVARCHAR(20)   NULL REFERENCES dbo.Applications(app_id),
    category       NVARCHAR(100)  NULL
);

CREATE TABLE dbo.QueryLog (
    log_id       BIGINT IDENTITY(1,1) PRIMARY KEY,
    user_query   NVARCHAR(1000) NOT NULL,
    matched_type NVARCHAR(10)   NOT NULL,   -- FAQ / APP / NONE
    matched_id   NVARCHAR(20)   NULL,
    teams_user   NVARCHAR(200)  NULL,
    created_at   DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME()
);
GO

INSERT INTO dbo.Applications
    (app_id, app_name, category, short_description, url, keywords, access_notes, owner_contact, status)
VALUES
 (N'APP001', N'HRMS Leave Portal', N'HR', N'Apply for leave, check leave balance and view holiday calendar.',
  N'https://intranet.example.com/hrms/leave', N'leave, vacation, holiday, sick, time off, absence, balance',
  N'All employees (SSO)', N'hr-helpdesk@example.com', N'Active'),
 (N'APP002', N'Timesheet System', N'Project', N'Fill and submit weekly timesheets against project codes.',
  N'https://intranet.example.com/timesheet', N'timesheet, hours, effort, booking, project code, weekly',
  N'All employees (SSO)', N'pmo@example.com', N'Active'),
 (N'APP003', N'Travel Desk', N'Admin', N'Raise travel requests, book flights and hotels for business travel.',
  N'https://intranet.example.com/travel', N'travel, trip, flight, hotel, visa, booking, business travel',
  N'Manager approval required', N'travel-desk@example.com', N'Active'),
 (N'APP004', N'Expense Claims', N'Finance', N'Submit expense claims and reimbursements with receipts.',
  N'https://intranet.example.com/expenses', N'expense, reimbursement, claim, receipt, bill, allowance',
  N'All employees (SSO)', N'finance-ops@example.com', N'Active'),
 (N'APP005', N'IT Service Desk', N'IT', N'Log IT tickets for laptop, software, VPN, access and password issues.',
  N'https://intranet.example.com/itsd', N'it, ticket, laptop, software, vpn, password, access, issue, support',
  N'All employees', N'it-helpdesk@example.com', N'Active'),
 (N'APP006', N'Payroll Self-Service', N'Finance', N'Download payslips, Form 16 and submit tax declarations.',
  N'https://intranet.example.com/payroll', N'payslip, salary, tax, form 16, declaration, payroll, investment',
  N'All employees (SSO + OTP)', N'payroll@example.com', N'Active'),
 (N'APP007', N'Skills Profile (HRMS)', N'HR', N'Update your skills, certifications and project experience.',
  N'https://intranet.example.com/hrms/skills', N'skills, certification, profile, competency, resume, experience',
  N'All employees (SSO)', N'hr-helpdesk@example.com', N'Active'),
 (N'APP008', N'Learning Hub', N'L&D', N'Enrol in trainings, courses and track mandatory learning.',
  N'https://intranet.example.com/learning', N'training, course, learning, certification, compliance, elearning',
  N'All employees', N'learning@example.com', N'Active'),
 (N'APP099', N'Old Leave System', N'HR', N'Retired - replaced by HRMS Leave Portal.',
  N'https://intranet.example.com/old-leave', N'leave', NULL, NULL, N'Retired');   -- excluded by the bot

INSERT INTO dbo.FAQs (faq_id, question, answer, related_app_id, category)
VALUES
 (N'FAQ001', N'How do I apply for leave?',
  N'Open the HRMS Leave Portal, choose **Apply Leave**, pick the leave type and dates, and submit. Your manager gets it for approval.',
  N'APP001', N'HR'),
 (N'FAQ002', N'Where do I submit my timesheet?',
  N'Timesheets are submitted weekly in the Timesheet System. Book hours against your project code before Friday EOD.',
  N'APP002', N'Project'),
 (N'FAQ003', N'How do I reset my password?',
  N'Raise a ticket in the IT Service Desk under **Access > Password Reset**, or use the self-service reset link on the login page.',
  N'APP005', N'IT'),
 (N'FAQ004', N'Where can I download my payslip?',
  N'Payslips are in Payroll Self-Service under **My Payslips**.',
  N'APP006', N'Finance');
GO

SELECT 'Applications' AS tbl, COUNT(*) AS rows_ FROM dbo.Applications
UNION ALL SELECT 'FAQs', COUNT(*) FROM dbo.FAQs
UNION ALL SELECT 'QueryLog', COUNT(*) FROM dbo.QueryLog;
GO
