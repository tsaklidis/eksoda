package io.eksoda.ui.navigation

sealed class AuthRoute(val route: String) {
    data object Graph : AuthRoute("auth_graph")
    data object Welcome : AuthRoute("welcome")
    data object Login : AuthRoute("login")
    data object Register : AuthRoute("register")
}

sealed class MainRoute(val route: String) {
    data object Graph : MainRoute("main_graph")
    data object Home : MainRoute("home")
    data object Receipts : MainRoute("receipts")
    data object Scan : MainRoute("scan")
    data object Insights : MainRoute("insights")
    data object Products : MainRoute("products")
}
