package io.eksoda.feature.products.review

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.paging.LoadState
import androidx.paging.compose.collectAsLazyPagingItems
import androidx.paging.compose.itemKey
import io.eksoda.core.network.model.ReviewItemResponse
import io.eksoda.core.ui.component.MoneyText
import io.eksoda.core.model.Money
import java.math.BigDecimal
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewScreen(
    onBackClick: () -> Unit,
    onNavigateToMatch: (String) -> Unit,
    onNavigateToCreate: (String, String) -> Unit,
    viewModel: ReviewViewModel = hiltViewModel()
) {
    val items = viewModel.items.collectAsLazyPagingItems()
    val uiState = viewModel.uiState

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Help us match these items") },
                navigationIcon = {
                    IconButton(onClick = onBackClick) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            if (items.loadState.refresh is LoadState.Loading) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            } else if (items.itemCount == 0 && items.loadState.refresh is LoadState.NotLoading) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Icon(
                        Icons.Default.Check,
                        contentDescription = null,
                        modifier = Modifier.size(64.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text("All caught up ✓", style = MaterialTheme.typography.headlineSmall)
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    items(
                        count = items.itemCount,
                        key = items.itemKey { it.id }
                    ) { index ->
                        val item = items[index]
                        if (item != null) {
                            ReviewCard(
                                item = item,
                                onMatchClick = { onNavigateToMatch(item.id) },
                                onCreateClick = { onNavigateToCreate(item.id, item.description) }
                            )
                        }
                    }
                }
            }

            if (uiState.isSubmitting) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth().align(Alignment.TopCenter))
            }

            uiState.successMessage?.let { msg ->
                Snackbar(
                    modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp),
                    action = { TextButton(onClick = viewModel::clearMessages) { Text("OK") } }
                ) { Text(msg) }
            }
        }
    }
}

@Composable
fun ReviewCard(
    item: ReviewItemResponse,
    onMatchClick: () -> Unit,
    onCreateClick: () -> Unit
) {
    val dateFormatter = DateTimeFormatter.ofPattern("MMM dd")
    val date = OffsetDateTime.parse(item.issued_at)

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = item.description,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${item.merchant_name} · ${date.format(dateFormatter)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                MoneyText(money = Money(BigDecimal(item.gross_amount), item.currency))
            }

            if (item.quantity != null) {
                Text(
                    text = "${item.quantity} ${item.unit ?: "x"}",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = onMatchClick) {
                    Text("Match to product")
                }
                Spacer(modifier = Modifier.width(8.dp))
                Button(onClick = onCreateClick) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("New product")
                }
            }
        }
    }
}
