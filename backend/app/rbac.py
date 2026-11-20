"""Role-based access control for NEXUS workspaces.

Matrix follows the product blueprint (owner / admin / manager / sales).
A membership's `grants` list adds blueprint "extra permissions" on top of its role.
Enforcement lives in the API dependencies; the UI only hides what the API would reject.
"""
from fastapi import Depends, HTTPException
from .auth import current_membership

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_SALES = "sales"
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES)

COMPANY_SETTINGS = "company.settings"
TEAM_VIEW = "team.view"
TEAM_MANAGE = "team.manage"
CONTACTS_VIEW_ALL = "contacts.view_all"
CONTACTS_VIEW_ASSIGNED = "contacts.view_assigned"
REPORTS_COMPANY = "reports.company"
REPORTS_OWN = "reports.own"
BILLING_VIEW = "billing.view"
BILLING_MANAGE = "billing.manage"
AI_SETTINGS_VIEW = "ai.settings.view"
AI_SETTINGS_MANAGE = "ai.settings.manage"
LEADS_VIEW_ALL = "leads.view_all"
CONTACTS_EXPORT = "contacts.export"
DEALS_DELETE = "deals.delete"
INTEGRATIONS_MANAGE = "integrations.manage"
REVENUE_VIEW = "revenue.view"

ROLE_PERMISSIONS = {
    ROLE_OWNER: {
        COMPANY_SETTINGS, TEAM_VIEW, TEAM_MANAGE,
        CONTACTS_VIEW_ALL, CONTACTS_VIEW_ASSIGNED,
        REPORTS_COMPANY, REPORTS_OWN,
        BILLING_VIEW, BILLING_MANAGE,
        AI_SETTINGS_VIEW, AI_SETTINGS_MANAGE,
        LEADS_VIEW_ALL, CONTACTS_EXPORT, DEALS_DELETE, INTEGRATIONS_MANAGE, REVENUE_VIEW,
    },
    ROLE_ADMIN: {
        COMPANY_SETTINGS, TEAM_VIEW, TEAM_MANAGE,
        CONTACTS_VIEW_ALL, CONTACTS_VIEW_ASSIGNED,
        REPORTS_COMPANY,
        BILLING_VIEW,
        AI_SETTINGS_VIEW, AI_SETTINGS_MANAGE,
        LEADS_VIEW_ALL, CONTACTS_EXPORT, DEALS_DELETE, INTEGRATIONS_MANAGE, REVENUE_VIEW,
    },
    ROLE_MANAGER: {
        TEAM_VIEW,
        CONTACTS_VIEW_ALL, CONTACTS_VIEW_ASSIGNED,
        REPORTS_COMPANY,
        AI_SETTINGS_VIEW,
    },
    ROLE_SALES: {
        TEAM_VIEW,
        CONTACTS_VIEW_ASSIGNED,
        REPORTS_OWN,
    },
}

# Blueprint "extra permissions" an owner/admin can add to any membership.
GRANTABLE = {
    LEADS_VIEW_ALL, CONTACTS_EXPORT, DEALS_DELETE,
    INTEGRATIONS_MANAGE, REVENUE_VIEW, BILLING_MANAGE,
    CONTACTS_VIEW_ALL, REPORTS_COMPANY,
}
# Grants only an owner may hand out.
OWNER_ONLY_GRANTS = {BILLING_MANAGE}


def permissions_for(role, grants):
    granted = {g for g in (grants or []) if g in GRANTABLE}
    return sorted(ROLE_PERMISSIONS.get(role, set()) | granted)


def has_permission(membership, permission):
    if permission in ROLE_PERMISSIONS.get(membership.role, set()):
        return True
    return permission in GRANTABLE and permission in (membership.grants or [])


def require(permission):
    """FastAPI dependency: 403 unless the active membership holds the permission."""
    def dependency(ctx=Depends(current_membership)):
        if not has_permission(ctx["membership"], permission):
            raise HTTPException(403, "This action requires the permission: " + permission)
        return ctx
    return dependency
