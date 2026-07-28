// GLOBAL STATE
let cartItems = [];
let currentTotal = 0;
let currentPaymentMethod = "";
let availableItemsList = []; // Array to store database items for the edit dropdown
let paymentInterval = null;  // Global variable for checking QR payment status

// Sounds
const beepSound = new Audio("/static/js/scanner-beep.mp3");
const kachingSound = new Audio("/static/js/kaching.mp3"); 

// PROFILE DROPDOWN
function toggleProfileMenu() {
    const dropdown = document.getElementById('profileDropdown');
    dropdown.classList.toggle('hidden');
}

// Close the dropdown if the user clicks random
window.onclick = function(event) {
    if (!event.target.closest('.profile-wrapper')) {
        const dropdown = document.getElementById('profileDropdown');
        if (dropdown && !dropdown.classList.contains('hidden')) {
            dropdown.classList.add('hidden');
        }
    }
}

function logoutStaff() {
    // Redirects to Flask logout route
    window.location.href = '/logout'; 
}

// NUMPAD INPUT
const inputField = document.getElementById('numpadInput');

function pressKey(val) {
    if (val === '.' && inputField.value.includes('.')) return;
    inputField.value += val;
}

function clearKey() {
    inputField.value = '';
}

// ADD ITEM MANUALLY (FROM DB)
async function addManual() {
    const itemId = inputField.value;

    if (!itemId) {
        alert("Enter Item ID");
        return;
    }

    try {
        const itemRes = await fetch(`/api/get_item/${itemId}`);
        const itemData = await itemRes.json();

        if (itemData.status !== "success") {
            alert("Item not found!");
            clearKey();
            return;
        }

        const weightRes = await fetch('/api/get_weight');
        const weightData = await weightRes.json();

        if (weightData.status !== "success") {
            alert(weightData.message);
            return;
        }

        const weight = parseFloat(weightData.weight);
        const price = weight * itemData.priceKg;

        cartItems.push({
            id: itemData.id,
            name: itemData.name,
            weight: weight,
            unitPrice: itemData.priceKg,
            price: price
        });

        beepSound.play();
        updateCartDisplay();

    } catch (error) {
        console.error(error);
        alert("Server connection error");
    }

    clearKey();
}

// AUTO DETECTION (YOLO, HX711)
async function detectItem() {
    const btn = document.getElementById('btnDetect');
    const originalText = btn.innerText;

    btn.innerText = "Detecting & Weighing...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/detect');
        const data = await response.json();

        if (data.status !== "success") {
            alert(data.message);
            return;
        }

        cartItems.push({
            id: data.id,
            name: data.item,
            weight: data.weight,
            unitPrice: data.price_per_kg,
            price: data.price
        });

        beepSound.play();
        updateCartDisplay();

    } catch (error) {
        console.error(error);
        alert("Detection failed.");
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

// UPDATE CART UI
function updateCartDisplay() {
    const cartBody = document.querySelector('.cart-body');
    const totalDisplay = document.getElementById('mainTotalDue');

    if (cartItems.length === 0) {
        cartBody.innerHTML = `
            <div class="empty-state">
                <p>No items added yet.</p>
                <p style="font-size: 0.85rem; margin-top: 5px;">Use camera or enter Item ID.</p>
            </div>
        `;
        currentTotal = 0;
        totalDisplay.innerText = "RM 0.00";
        return;
    }

    let html = "";
    currentTotal = 0;

    cartItems.forEach((item, index) => {
        let actionButtons = `
            <button class="btn-icon btn-icon-edit" onclick="handleEditAction(${index})" title="Edit Item">✏️</button>
            <button class="btn-icon btn-icon-delete" onclick="handleDeleteAction(${index})" title="Remove Item">✖</button>
        `;

        html += `
        <div class="cart-item-row">
            <div class="cart-item-name">${item.name.replace(/_/g, ' ')}</div>
            <div class="cart-item-weight">${item.weight.toFixed(3)} kg</div>
            <div class="cart-item-price">RM ${item.price.toFixed(2)}</div>
            <div class="cart-item-actions">
                ${actionButtons}
            </div>
        </div>
        `;
        currentTotal += item.price;
    });

    cartBody.innerHTML = html;
    totalDisplay.innerText = "RM " + roundToNearest5Cents(currentTotal);

    cartBody.scrollTop = cartBody.scrollHeight;
}

function roundToNearest5Cents(amount){
    let roundedAmount = Math.round(amount*20)/20;
    return roundedAmount.toFixed(2);
}

// ADMIN OVERRIDE HELPER
let adminResolve = null;

function checkAdminOverride(actionName) {
    return new Promise((resolve) => {
        // Bypass if user is already an admin
        if (typeof currentUserRole !== 'undefined' && currentUserRole.toLowerCase() === 'admin') {
            resolve(true);
            return;
        }

        // Store the promise resolver 
        adminResolve = resolve;
        
        // Reset modal fields
        document.getElementById('adminAuthActionText').innerText = actionName;
        document.getElementById('adminIdInput').value = '';
        document.getElementById('adminPasswordInput').value = '';
        document.getElementById('adminPasswordInput').type = 'password'; 
        document.getElementById('togglePasswordBtn').innerText = 'Show';
        
        // Show the custom modal
        document.getElementById('adminAuthModal').style.display = 'flex';
    });
}

function closeAdminAuthModal() {
    document.getElementById('adminAuthModal').style.display = 'none';
    if (adminResolve) {
        adminResolve(false); // Cancel the action
        adminResolve = null;
    }
}

function togglePasswordVisibility() {
    const passInput = document.getElementById('adminPasswordInput');
    const toggleBtn = document.getElementById('togglePasswordBtn');
    
    if (passInput.type === 'password') {
        passInput.type = 'text';
        toggleBtn.innerText = 'Hide';
    } else {
        passInput.type = 'password';
        toggleBtn.innerText = 'Show';
    }
}

async function submitAdminAuth() {
    const enteredId = document.getElementById('adminIdInput').value;
    const enteredPass = document.getElementById('adminPasswordInput').value;
    const actionName = document.getElementById('adminAuthActionText').innerText;

    if (!enteredId || !enteredPass) {
        alert("Please enter both Admin ID and Password.");
        return;
    }

    try {
        let response = await fetch('/api/verify_admin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ admin_id: enteredId, password: enteredPass })
        });

        let result = await response.json();

        if (result.success) {
            alert(`✅ Authorization accepted. Proceeding to ${actionName}.`);
            document.getElementById('adminAuthModal').style.display = 'none';
            if (adminResolve) {
                adminResolve(true);
                adminResolve = null;
            }
        } else {
            alert("❌ Access Denied: " + result.message);
            document.getElementById('adminPasswordInput').value = ''; // clear password on fail
        }
    } catch (error) {
        console.error("Verification error:", error);
        alert("❌ Error communicating with server.");
        closeAdminAuthModal();
    }
}

// DELETE ITEM
async function handleDeleteAction(index) {
    const isAuthorized = await checkAdminOverride('delete');
    if (isAuthorized) {
        if (typeof currentUserRole !== 'undefined' && currentUserRole.toLowerCase() === 'admin' && !confirm("Remove item?")) return;
        cartItems.splice(index, 1);
        updateCartDisplay();
    }
}

// EDIT ITEM
async function fetchItemsFromDB() {
    if (availableItemsList.length > 0) return;

    try {
        const response = await fetch('/api/get_all_items');
        const data = await response.json();
        if (data.status === "success") {
            availableItemsList = data.items;
        }
    } catch (error) {
        console.error("Failed to fetch database items:", error);
    }
}

async function handleEditAction(index) {
    await fetchItemsFromDB();
    openEditModal(index);
}

function openEditModal(index) {
    const currentItem = cartItems[index];
    document.getElementById('editItemIndex').value = index;
    
    const selectElement = document.getElementById('editItemSelect');
    if (selectElement) {
        selectElement.innerHTML = ''; 
        
        availableItemsList.forEach(dbItem => {
            let option = document.createElement('option');
            option.value = dbItem.id;
            option.text = dbItem.name.replace(/_/g, ' ').toUpperCase();
            option.dataset.price = dbItem.priceKg;
            option.dataset.name = dbItem.name;
            
            if (dbItem.name === currentItem.name) {
                option.selected = true;
            }
            selectElement.appendChild(option);
        });
    }
    
    document.getElementById('editModal').style.display = 'flex';
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
}

function saveEditedItem() {
    const index = document.getElementById('editItemIndex').value;
    const selectElement = document.getElementById('editItemSelect');
    
    if (!selectElement || selectElement.selectedIndex === -1) {
        alert("Please select an item.");
        return;
    }

    const selectedOption = selectElement.options[selectElement.selectedIndex];
    
    const newId = selectedOption.value;
    const newName = selectedOption.dataset.name;
    const newUnitPrice = parseFloat(selectedOption.dataset.price);

    // Retain the original weight
    const originalWeight = cartItems[index].weight;

    // Update cart items with new selection but keep weight
    cartItems[index].id = newId;
    cartItems[index].name = newName;
    cartItems[index].unitPrice = newUnitPrice;
    cartItems[index].price = originalWeight * newUnitPrice; // Recalculate price based on retained weight

    updateCartDisplay();
    closeEditModal();
}

// PAYMENT MODAL CONTROL
function openPaymentGateway() {
    if (cartItems.length === 0) {
        alert("Cart is empty!");
        return;
    }
    document.getElementById('paymentGateway').style.display = 'flex';
    document.getElementById('modalTotalAmount').innerText = "RM " + roundToNearest5Cents(currentTotal);
    
    document.getElementById('displayChange').innerText = ""; 
}

function closePaymentGateway() {
    // Clear any existing intervals if closed halfway
    if (paymentInterval) clearInterval(paymentInterval); 

    // Reset UI blocks
    document.getElementById('paymentGateway').style.display = 'none';
    document.getElementById('pg-step-select').style.display = 'block';
    
    // Reset grids and hide QR/Success states
    if (document.getElementById('paymentButtonsGrid')) {
        document.getElementById('paymentButtonsGrid').style.display = 'grid'; 
    }
    if (document.getElementById('qr-container')) {
        document.getElementById('qr-container').style.display = 'none';
    }

    document.getElementById('pg-step-cash').style.display = 'none';
    document.getElementById('pg-step-success').style.display = 'none';
    document.getElementById('pg-step-processing').style.display = 'none';
}

function backToSelectMethod() {
    document.getElementById('pg-step-cash').style.display = 'none';
    document.getElementById('pg-step-select').style.display = 'block';
}

// SELECT PAYMENT
function selectPaymentMethod(method) {
    currentPaymentMethod = method;

    if (method === "Cash") {
        document.getElementById('pg-step-select').style.display = 'none';
        document.getElementById('pg-step-cash').style.display = 'block';
        document.getElementById('inputTendered').value = "";
        validateCash(); 
    } else {
        processNonCash();
    }
}

// CASH PAYMENT
function validateCash() {
    const tendered = parseFloat(document.getElementById('inputTendered').value);
    const roundedTotal = parseFloat(roundToNearest5Cents(currentTotal));
    const btn = document.getElementById('btnConfirmCash');
    btn.disabled = isNaN(tendered) || (tendered < roundedTotal);
}

function processCashPayment() {
    const tendered = parseFloat(document.getElementById('inputTendered').value);
    const roundedTotal = parseFloat(roundToNearest5Cents(currentTotal));
    const change = tendered - roundedTotal;
    showSuccess(change);
}

// QR CODE API
function startQRPaymentFlow() {
    let totalText = document.getElementById('modalTotalAmount').innerText;
    let amount = parseFloat(totalText.replace('RM ', '').trim());

    if (amount <= 0) {
        alert("Amount must be greater than 0");
        return;
    }

    // Hide payment buttons, prepare to show QR
    document.getElementById('paymentButtonsGrid').style.display = 'none';
    
    // Call function to fetch QR from backend
    generateQRPayment(amount); 
}

async function generateQRPayment(amount) {
    const qrStatus = document.getElementById('qr-status');
    let qrImage = document.getElementById('qr-image');
    
    document.getElementById('qr-container').style.display = 'block';
    qrStatus.innerText = "Generating QR Code...";
    qrStatus.style.color = "#2563eb";

    // 1. REVERT IFRAME BACK TO AN IMAGE (IMG) TAG IF IT EXISTS
    if (qrImage && qrImage.tagName.toLowerCase() === 'iframe') {
        const img = document.createElement('img');
        img.id = 'qr-image';
        img.alt = 'QR Code';
        img.style.width = '100%';
        img.style.maxWidth = '300px'; // Keeps the QR code size neat and clean
        img.style.margin = '0 auto';
        img.style.display = 'block';
        img.style.borderRadius = '8px';
        
        qrImage.parentNode.replaceChild(img, qrImage);
        qrImage = img; // Update reference
    }

    qrImage.src = ""; 

    try {
        // Request the backend to create a bill in ToyyibPay
        const response = await fetch('/api/create_qr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: amount })
        });

        const data = await response.json();
        console.log("Response from server:", data);

        if (data.status === 'success' && data.bill_code) {
            const billCode = data.bill_code;
            
            // 2. GET THE TOYYIBPAY PAYMENT URL
            const paymentUrl = `https://dev.toyyibpay.com/${billCode}`;
            
            // 3. GENERATE A CLEAN QR IMAGE USING A QR GENERATOR API
            const qrImageUrl = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(paymentUrl)}`;
            
            // 4. DISPLAY THE QR IMAGE ON THE SCREEN
            qrImage.src = qrImageUrl;
            qrStatus.innerText = "Scan The QR";
            
            // Start checking for payment status automatically
            checkPaymentStatus(billCode);
        } else {
            qrStatus.innerText = "Error: " + (data.message || "Invalid Response");
            qrStatus.style.color = "red";
        }

    } catch (error) {
        console.error("QR Generation Error:", error);
        qrStatus.innerText = "Network Error. Please check terminal.";
        qrStatus.style.color = "red";
    }
}

function checkPaymentStatus(billCode) {
    // Clear any existing intervals
    if (paymentInterval) clearInterval(paymentInterval);

    // Set interval to check every 3 seconds (3000 ms)
    paymentInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/check_payment_status/${billCode}`);
            const data = await response.json();

            if (data.status === 'paid') {
                clearInterval(paymentInterval); 
                
                // play sound if transaction success
                kachingSound.play().catch(error => {
                    console.log("Browser blocked audio (Autoplay Policy):", error);
                });
                
                // Hide QR container and show success container
                document.getElementById('qr-container').style.display = 'none';
                document.getElementById('pg-step-success').style.display = 'block';
                
                // Clear any remaining change text
                document.getElementById('displayChange').innerText = ""; 
                
                // Set payment method to QR Pay so backend saves it correctly
                currentPaymentMethod = "E-Wallet";
            }
        } catch (error) {
            console.error("Error checking payment status:", error);
        }
    }, 3000); 
}

function cancelQRPayment() {
    // Stop the auto-checking
    if (paymentInterval) clearInterval(paymentInterval);
    
    // Hide QR section and bring back the Cash/QR buttons
    document.getElementById('qr-container').style.display = 'none';
    document.getElementById('paymentButtonsGrid').style.display = 'grid'; 
}

// SUCCESS SCREEN
function showSuccess(change) {
    document.getElementById('pg-step-processing').style.display = 'none';
    document.getElementById('pg-step-cash').style.display = 'none';
    document.getElementById('pg-step-success').style.display = 'block';

    // If payment method is not Cash, force change to 0
    if (currentPaymentMethod !== "Cash") {
        document.getElementById('displayChange').innerText = "";
    } else {
        // If Cash, only then display the change (if any)
        if (change > 0) {
            document.getElementById('displayChange').innerText = "Change to return: RM " + change.toFixed(2);
        } else {
            document.getElementById('displayChange').innerText = "";
        }
    }
}

// COMPLETE TRANSACTION TO SAVE TO DB
async function completeTransaction() {
    try {
        const response = await fetch('/api/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                total_amount: parseFloat(roundToNearest5Cents(currentTotal)),
                payment_method: currentPaymentMethod,
                items: cartItems
            })
        });

        const data = await response.json();

        if (data.status === "success") {
            cartItems = [];
            currentTotal = 0;
            closePaymentGateway();
            updateCartDisplay();
        } else {
            alert("Error: " + data.message);
        }

    } catch (error) {
        console.error(error);
        alert("Failed to save transaction");
    }
}

// TODAY'S SALE
function openDailySalesModal() {
    // Hide the profile dropdown so it's not in the way
    document.getElementById('profileDropdown').classList.add('hidden');
    
    // Show the modal
    const modal = document.getElementById('dailySalesModal');
    modal.style.display = 'flex';
    
    // Fetch the data from the backend
    fetchDailySales();
}

function closeDailySalesModal() {
    document.getElementById('dailySalesModal').style.display = 'none';
}

async function fetchDailySales() {
    try {
        const response = await fetch('/api/staff_daily_sales');
        const data = await response.json();
        
        if (data.status === 'success') {
            // Update Summary Cards
            document.getElementById('shiftTotalAmount').innerText = `RM ${data.total_earnings.toFixed(2)}`;
            document.getElementById('shiftTransactionCount').innerText = data.total_transactions;
            
            // Update Table
            const tbody = document.getElementById('shiftSalesTableBody');
            tbody.innerHTML = ''; // Clear loading message
            
            if (data.transactions.length === 0) {
                // Updated colspan to 4 since we added the "Receipt" column
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 20px; color: #94a3b8;">No transactions yet today.</td></tr>';
                return;
            }
            
            data.transactions.forEach(trx => {
                const row = document.createElement('tr');
                row.style.borderBottom = '1px solid #f1f5f9';
                
                // Added the 4th column for the "View Details" button
                row.innerHTML = `
                    <td style="padding: 12px 15px; color: #334155; font-weight: 500;">#${trx.receiptId}</td>
                    <td style="padding: 12px 15px; color: #64748b;">
                        <span style="background: #f1f5f9; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem;">${trx.payment_method}</span>
                    </td>
                    <td style="padding: 12px 15px; color: #0f172a; font-weight: bold; text-align: right;">RM ${trx.total_amount.toFixed(2)}</td>
                    <td style="padding: 12px 15px; text-align: center;">
                        <a href="/cashier/receipt/${trx.receiptId}" 
                           style="text-decoration: none; background: #2563eb; color: white; padding: 5px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: 500;">
                           View Details
                        </a>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }
    } catch (error) {
        console.error("Error fetching shift data:", error);
        // Updated colspan to 4 here as well
        document.getElementById('shiftSalesTableBody').innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 20px; color: #ef4444;">Failed to load data.</td></tr>';
    }
}
