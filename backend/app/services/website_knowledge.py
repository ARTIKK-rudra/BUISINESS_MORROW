"""Safe, code-reviewed website knowledge for the in-product assistant.

This registry deliberately contains no source files, credentials, tenant data, or
infrastructure details.  Keep it synchronized with verified routes and features.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WebsiteFeature:
    name: str
    route: str
    purpose: str
    access: str
    actions: str
    workflow: str
    status: str = "implemented"
    related: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    common_errors: tuple[str, ...] = ()


FEATURES: tuple[WebsiteFeature, ...] = (
    WebsiteFeature("Dashboard", "/", "Business command center with reporting shortcuts and visual summaries.", "All signed-in roles with business access.", "Review summaries and open linked modules.", "Use it to decide whether to review sales, inventory, forecasts, or recommendations.", "implemented", ("Sales", "Inventory", "Forecasting"), ("An authenticated business membership for live data",), ("If the page shows sample data, the frontend is in preview mode.",)),
    WebsiteFeature("Sales", "/sales", "Review recorded sales and payment activity.", "Roles with sales read access.", "View sales records and reporting views.", "Completed orders feed sales reporting.", "implemented", ("Orders", "Ledger"), ("Recorded completed orders",), ("An empty result means no matching sales are recorded, not that sales were estimated.",)),
    WebsiteFeature("Point of sale", "/pos", "A frontend checkout workspace for building a cart and receipt preview.", "Roles with sales access.", "Search products, change quantities and preview a receipt.", "Payment processing is explicitly a preview until a payment API is connected.", "implemented", ("Products", "Sales"), ("Product catalog data for live mode",), ("A receipt preview is not a completed payment or persisted sale.",)),
    WebsiteFeature("Orders", "/orders", "Order-management workspace.", "Roles with sales read access.", "Review order statuses in the current workspace view.", "Pending orders can contribute to provision shortage calculations when recipes are configured.", "preview", ("Sales", "Inventory")),
    WebsiteFeature("Inventory", "/inventory", "Track stock, thresholds, expiry, movements, and rule-based risk.", "Roles with inventory read access.", "Review levels and inventory records.", "Low or depleted stock can feed the provision workflow; this is distinct from a model prediction.", "implemented", ("Products", "Purchases", "Provision agent"), ("Inventory records and configured thresholds",), ("A low-stock state is rule-based unless a stored ML prediction is explicitly shown.",)),
    WebsiteFeature("Products", "/products", "Maintain the restaurant product catalog.", "Roles with catalog access.", "Review catalog items in the current workspace view.", "Products can be sold, stocked, or associated with recipes.", "preview", ("Inventory", "Point of sale")),
    WebsiteFeature("Suppliers", "/suppliers", "Manage registered suppliers and their product offers.", "Roles with procurement read access.", "Review suppliers and supplier intelligence.", "Supplier offers and lead time support procurement review; no supplier is contacted automatically.", "implemented", ("Purchases", "Provision agent"), ("Tenant-scoped supplier records",), ("No active suppliers means none are recorded for this business; it never triggers a call.",)),
    WebsiteFeature("Purchases", "/purchases", "Review purchase-order and receiving activity.", "Roles with procurement read access; owner approval remains required for purchasing actions.", "Review purchase records in the current workspace view.", "Approved procurement can create a purchase; receiving updates inventory.", "preview", ("Inventory", "Suppliers")),
    WebsiteFeature("Invoice capture", "/invoices", "Upload a supplier invoice for OCR extraction and human review.", "Roles with procurement access.", "Create and review an OCR draft.", "Uncertain OCR data requires user confirmation before it becomes a record.", "implemented", ("Purchases", "Suppliers"), ("A supported invoice file and supplier record",), ("OCR extraction can require manual correction; uploads are not committed automatically.",)),
    WebsiteFeature("Expenses", "/expenses", "Expense reporting workspace.", "Roles with finance read access.", "Review expense information in the current workspace view.", "Recorded expenses contribute to financial reporting.", "preview", ("Profit and loss", "Ledger")),
    WebsiteFeature("Ledger", "/ledger", "Reporting view of automatically generated financial activity.", "Roles with finance read access.", "Review entries and source events.", "Users do not manually maintain the ledger; business events generate entries.", "preview", ("Sales", "Expenses", "Profit and loss")),
    WebsiteFeature("Profit and loss", "/profit-loss", "Financial performance reporting.", "Roles with finance read access.", "Review revenue, costs, expenses, and profit summaries.", "Uses recorded business and ledger information.", "preview", ("Ledger", "Expenses")),
    WebsiteFeature("Reports", "/reports", "Reporting workspace for business performance.", "Roles with finance or insights access.", "Review report categories in the current workspace view.", "Exports are displayed as unavailable until a connected export service exists.", "preview", ("Analytics", "Profit and loss")),
    WebsiteFeature("Business assistant", "/assistant", "Text assistant for verified business and website questions.", "Roles with insights read access.", "Ask read-only questions.", "Answers use tenant-scoped database queries and safe website knowledge.", "implemented", ("Voice assistant", "Analytics"), ("An authenticated business membership",), ("Unsupported questions are identified instead of answered with invented data.",)),
    WebsiteFeature("Forecasting", "/forecasting", "Historical-versus-forecast workspace.", "Roles with insights read access.", "Review stored forecast displays.", "Forecasts only guide planning and never place orders.", "preview", ("Recommendations", "Inventory")),
    WebsiteFeature("AI insights", "/ai-insights", "AI insight workspace.", "Roles with insights read access.", "Review the current workspace presentation.", "Only stored, supported findings should be treated as operational data.", "preview", ("Anomalies", "Recommendations")),
    WebsiteFeature("Anomalies", "/anomalies", "Anomaly investigation workspace.", "Roles with insights read access.", "Review anomalies in the current workspace view.", "Stored anomalies can be queried; absence of one is not a claim that no risk exists.", "preview", ("Refunds", "AI insights")),
    WebsiteFeature("Recommendations", "/recommendations", "Review recommendation proposals and approval states.", "Roles with insights or procurement access; approvals require owner authority.", "Review recommendation details.", "Recommendations do not automatically create purchases.", "implemented", ("Forecasting", "Provision agent"), ("Stored recommendation records",), ("A recommendation is not a purchase order and needs the normal approval workflow.",)),
    WebsiteFeature("Voice assistant", "/voice-assistant", "Browser speech and text interface for this website-aware assistant.", "Roles with insights read access.", "Ask questions, navigate, and use optional browser or Gemini transcription.", "Telephone providers remain disabled; no calls or purchases are initiated here.", "implemented", ("Business assistant", "Provision agent"), ("Browser speech support or the typed-question fallback",), ("If browser speech services are unavailable, use typed input; Gemini recording requires a configured key.",)),
    WebsiteFeature("Provision agent", "/provision", "Permission-controlled local procurement workflow.", "Owner and authorized roles according to backend permissions.", "Start a demo or review shortage, manager, supplier, and approval stages.", "Shortage → owner supplier-contact approval → manager quantities → supplier quotation → separate owner purchase approval. No live calls in test mode.", "implemented", ("Inventory", "Suppliers", "Purchases"), ("Shortage data and an authenticated, authorized user",), ("Calling providers remain disabled; missing recipe/order data is reported as a data-quality issue.",)),
    WebsiteFeature("Analytics", "/analytics", "Analytics workspace.", "Roles with insights read access.", "Review analytics presentation.", "Uses recorded information where a connected data view exists; current generic workspace is a preview.", "preview", ("Reports", "Dashboard")),
    WebsiteFeature("Notifications", "/notifications", "Notification center.", "Signed-in users with business access.", "Review notification records.", "Notifications can reflect business events; no unsupported channels are implied.", "implemented", (), ("An authenticated business membership",), ("An empty center means no matching notification records are available.",)),
    WebsiteFeature("Audit log", "/audit-log", "Activity-history workspace.", "Owner/authorized users as enforced by backend.", "Review audit information in the current workspace view.", "Meaningful backend actions are auditable.", "preview"),
    WebsiteFeature("Settings", "/settings", "Workspace settings presentation.", "Owner or authorized users according to backend permissions.", "Review settings sections.", "Unavailable controls are intentionally disabled rather than silently changing configuration.", "preview"),
)


def feature_for_route(route: str | None) -> WebsiteFeature | None:
    return next((feature for feature in FEATURES if feature.route == route), None)


def find_feature(question: str, route: str | None = None) -> WebsiteFeature | None:
    text = question.lower()
    if any(phrase in text for phrase in ("this page", "here", "this screen", "what can i do")):
        return feature_for_route(route)
    return next(
        (
            feature
            for feature in FEATURES
            if feature.name.lower() in text
            or feature.name.lower().rstrip("s") in text
            or (feature.route != "/" and feature.route.lstrip("/") in text)
        ),
        None,
    )


def overview() -> str:
    implemented = [feature.name for feature in FEATURES if feature.status == "implemented"]
    previews = [feature.name for feature in FEATURES if feature.status == "preview"]
    return (
        "Morrow is a restaurant business command center. Its implemented operational modules include "
        + ", ".join(implemented)
        + ". Several additional workspace pages are currently design previews: "
        + ", ".join(previews)
        + ". I can explain either category, but I will not describe a preview as a live workflow."
    )
