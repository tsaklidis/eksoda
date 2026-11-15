package io.eksoda.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import io.eksoda.MainUiState
import io.eksoda.MainViewModel
import io.eksoda.feature.auth.login.LoginScreen
import io.eksoda.feature.auth.register.RegisterScreen
import io.eksoda.feature.auth.welcome.WelcomeScreen
import io.eksoda.feature.home.HomeScreen
import io.eksoda.feature.household.picker.HouseholdPickerScreen
import io.eksoda.feature.receipts.detail.ReceiptDetailScreen
import io.eksoda.feature.receipts.list.ReceiptListScreen
import io.eksoda.feature.scan.ScanScreen
import io.eksoda.ui.navigation.AuthRoute
import io.eksoda.ui.navigation.MainRoute

@Composable
fun EksodaApp(
    viewModel: MainViewModel = hiltViewModel()
) {
    val navController = rememberNavController()
    val uiState by viewModel.uiState.collectAsState()

    when (uiState) {
        MainUiState.Loading -> {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }
        MainUiState.Unauthenticated -> {
            NavHost(navController = navController, startDestination = AuthRoute.Welcome.route) {
                composable(AuthRoute.Welcome.route) {
                    WelcomeScreen(
                        onNavigateToLogin = { navController.navigate(AuthRoute.Login.route) },
                        onNavigateToRegister = { navController.navigate(AuthRoute.Register.route) }
                    )
                }
                composable(AuthRoute.Login.route) {
                    LoginScreen(
                        onLoginSuccess = { /* MainViewModel will update state */ },
                        onNavigateToRegister = { navController.navigate(AuthRoute.Register.route) }
                    )
                }
                composable(AuthRoute.Register.route) {
                    RegisterScreen(
                        onRegisterSuccess = { /* MainViewModel will update state */ },
                        onNavigateToLogin = { navController.popBackStack() }
                    )
                }
            }
        }
        MainUiState.HouseholdSelectionRequired -> {
            HouseholdPickerScreen(
                onNavigateToJoin = { /* TODO: Navigate to Join feature */ }
            )
        }
        MainUiState.Authenticated -> {
            val navBackStackEntry by navController.currentBackStackEntryAsState()
            val currentDestination = navBackStackEntry?.destination

            Scaffold(
                bottomBar = {
                    if (shouldShowBottomBar(currentDestination)) {
                        EksodaBottomBar(
                            destinations = listOf(
                                BottomBarDestination.Home,
                                BottomBarDestination.Receipts,
                                BottomBarDestination.Scan,
                                BottomBarDestination.Insights,
                                BottomBarDestination.Products
                            ),
                            onNavigateToDestination = { destination ->
                                if (destination == BottomBarDestination.Scan) {
                                    navController.navigate(MainRoute.Scan.route)
                                } else {
                                    navController.navigate(destination.route) {
                                        popUpTo(navController.graph.findStartDestination().id) {
                                            saveState = true
                                        }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            },
                            currentDestination = currentDestination
                        )
                    }
                }
            ) { padding ->
                NavHost(
                    navController = navController,
                    startDestination = MainRoute.Home.route,
                    modifier = Modifier.padding(padding)
                ) {
                    composable(MainRoute.Home.route) {
                        HomeScreen(
                            onNavigateToReceipts = { navController.navigate(MainRoute.Receipts.route) },
                            onNavigateToInsights = { navController.navigate(MainRoute.Insights.route) },
                            onNavigateToReview = { /* TODO */ },
                            onNavigateToImports = { /* TODO */ },
                            onNavigateToAccount = { /* TODO */ }
                        )
                    }
                    composable(MainRoute.Receipts.route) {
                        ReceiptListScreen(
                            onReceiptClick = { id -> navController.navigate("receipt/$id") },
                            onFilterClick = { /* TODO */ }
                        )
                    }
                    composable("receipt/{receiptId}") {
                        ReceiptDetailScreen(
                            onBackClick = { navController.popBackStack() },
                            onProductClick = { /* TODO */ }
                        )
                    }
                    composable(MainRoute.Scan.route) {
                        ScanScreen(
                            onClose = { navController.popBackStack() }
                        )
                    }
                    composable(MainRoute.Insights.route) {
                        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Text("Insights Dashboard (Milestone A4)")
                        }
                    }
                    composable(MainRoute.Products.route) {
                        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Text("Products List (Milestone A5)")
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun EksodaBottomBar(
    destinations: List<BottomBarDestination>,
    onNavigateToDestination: (BottomBarDestination) -> Unit,
    currentDestination: NavDestination?
) {
    NavigationBar {
        destinations.forEach { destination ->
            val selected = currentDestination.isTopLevelDestinationInHierarchy(destination)
            NavigationBarItem(
                selected = selected,
                onClick = { onNavigateToDestination(destination) },
                icon = {
                    Icon(
                        imageVector = if (selected) destination.selectedIcon else destination.unselectedIcon,
                        contentDescription = null
                    )
                },
                label = { Text(destination.label) }
            )
        }
    }
}

private fun NavDestination?.isTopLevelDestinationInHierarchy(destination: BottomBarDestination) =
    this?.hierarchy?.any {
        it.route?.contains(destination.route, true) ?: false
    } ?: false

private fun shouldShowBottomBar(destination: NavDestination?): Boolean {
    val route = destination?.route ?: return false
    return route == MainRoute.Home.route ||
            route == MainRoute.Receipts.route ||
            route == MainRoute.Insights.route ||
            route == MainRoute.Products.route
}

sealed class BottomBarDestination(
    val route: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector,
    val label: String
) {
    object Home : BottomBarDestination(MainRoute.Home.route, Icons.Default.Home, Icons.Default.Home, "Home")
    object Receipts : BottomBarDestination(MainRoute.Receipts.route, Icons.Default.Receipt, Icons.Default.Receipt, "Receipts")
    object Scan : BottomBarDestination(MainRoute.Scan.route, Icons.Default.QrCodeScanner, Icons.Default.QrCodeScanner, "Scan")
    object Insights : BottomBarDestination(MainRoute.Insights.route, Icons.Default.Insights, Icons.Default.Insights, "Insights")
    object Products : BottomBarDestination(MainRoute.Products.route, Icons.Default.ShoppingBag, Icons.Default.ShoppingBag, "Products")
}
