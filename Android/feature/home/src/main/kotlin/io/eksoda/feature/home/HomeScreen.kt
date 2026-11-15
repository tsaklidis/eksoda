package io.eksoda.feature.home

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import io.eksoda.core.model.Money
import io.eksoda.core.network.model.SummaryResponse
import io.eksoda.core.ui.component.MoneyText

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onNavigateToReceipts: () -> Unit,
    onNavigateToInsights: () -> Unit,
    onNavigateToReview: () -> Unit,
    onNavigateToImports: () -> Unit,
    onNavigateToAccount: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel()
) {
    val uiState = viewModel.uiState

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(uiState.householdName.ifEmpty { "Eksoda" }) },
                actions = {
                    IconButton(onClick = onNavigateToAccount) {
                        Icon(Icons.Default.AccountCircle, contentDescription = "Account")
                    }
                }
            )
        }
    ) { padding ->
        if (uiState.isLoading && uiState.summary == null) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp)
            ) {
                uiState.summary?.let { summary ->
                    SpendingCard(
                        summary = summary,
                        onClick = onNavigateToInsights
                    )
                    Spacer(modifier = Modifier.height(24.dp))
                    
                    if (summary.needs_review_count > 0) {
                        ReviewBadge(
                            count = summary.needs_review_count,
                            onClick = onNavigateToReview
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }

                Text(
                    text = "Quick Actions",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
                
                Row(modifier = Modifier.fillMaxWidth()) {
                    ActionCard(
                        title = "Receipts",
                        icon = Icons.Default.Receipt,
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateToReceipts
                    )
                    Spacer(modifier = Modifier.width(16.dp))
                    ActionCard(
                        title = "Imports",
                        icon = Icons.Default.History,
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateToImports
                    )
                }
                
                Spacer(modifier = Modifier.height(32.dp))
                
                if (uiState.error != null) {
                    Text(
                        text = uiState.error!!,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                    Button(onClick = viewModel::loadDashboard) {
                        Text("Retry")
                    }
                }
            }
        }
    }
}

@Composable
fun SpendingCard(
    summary: SummaryResponse,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(modifier = Modifier.padding(24.dp)) {
            Text(
                text = "Spent this month",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )
            Row(
                verticalAlignment = Alignment.Bottom,
                modifier = Modifier.padding(top = 8.dp)
            ) {
                MoneyText(
                    money = Money.fromString(summary.current.spending, summary.currency),
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.alignByBaseline()
                )
                Spacer(modifier = Modifier.width(8.dp))
                if (summary.change_percent != null) {
                    val isIncrease = summary.change_percent!! > 0
                    Text(
                        text = "${if (isIncrease) "+" else ""}${summary.change_percent}%",
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (isIncrease) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 4.dp).alignByBaseline()
                    )
                }
            }
            Text(
                text = "${summary.current.receipt_count} receipts",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f),
                modifier = Modifier.padding(top = 8.dp)
            )
        }
    }
}

@Composable
fun ReviewBadge(
    count: Int,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        color = MaterialTheme.colorScheme.errorContainer,
        contentColor = MaterialTheme.colorScheme.onErrorContainer,
        shape = MaterialTheme.shapes.medium
    ) {
        Row(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Default.Warning, contentDescription = null)
            Spacer(modifier = Modifier.width(16.dp))
            Text(
                text = "$count items to review",
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f)
            )
            Icon(Icons.Default.ArrowForward, contentDescription = null)
        }
    }
}

@Composable
fun ActionCard(
    title: String,
    icon: ImageVector,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    OutlinedCard(
        modifier = modifier.height(100.dp).clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(icon, contentDescription = null)
            Spacer(modifier = Modifier.height(8.dp))
            Text(text = title, style = MaterialTheme.typography.labelLarge)
        }
    }
}
