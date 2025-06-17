// category-service.js

require('dotenv').config();
const express = require('express');
const jwt = require('jsonwebtoken');
const { MongoClient, ObjectId } = require('mongodb');

const app = express();
app.use(express.json());

const MONGO_URI = process.env.MONGODB_URI;
const PORT = process.env.PORT || 5003;
const JWT_SECRET = process.env.JWT_SECRET;

let db, categories_collection;

// System categories (identical to your Python list)
const SYSTEM_CATEGORIES = [
    { name: 'Food',         type: 'expense', system: true },
    { name: 'Transport',    type: 'expense', system: true },
    { name: 'Entertainment',type: 'expense', system: true },
    { name: 'Utilities',    type: 'expense', system: true },
    { name: 'Healthcare',   type: 'expense', system: true },
    { name: 'Salary',       type: 'income',  system: true },
    { name: 'Business',     type: 'income',  system: true },
    { name: 'Investment',   type: 'income',  system: true },
];

// JWT verification
function verifyJwtToken(token) {
    try {
        return jwt.verify(token, JWT_SECRET);
    } catch (err) {
        return null;
    }
}

// User extraction middleware
function getCurrentUser(req) {
    const user = req.header('X-User');
    const role = req.header('X-Role');
    if (user && role) return { Username: user, Role: role };

    const auth = req.header('Authorization');
    if (auth && auth.startsWith('Bearer ')) {
        const payload = verifyJwtToken(auth.split(' ')[1]);
        return payload || null;
    }
    return null;
}

// Auth middlewares
function requireAuth(req, res, next) {
    const user = getCurrentUser(req);
    if (!user || !user.Username) {
        return res.status(401).json({ error: "Authentication required" });
    }
    req.user = user;
    next();
}
function requireAdmin(req, res, next) {
    const user = getCurrentUser(req);
    if (!user || user.Role !== "Admin") {
        return res.status(403).json({ error: "Admin access required" });
    }
    req.user = user;
    next();
}

// Health check
app.get("/health", (req, res) => {
    res.json({ status: "Category Service running", port: PORT });
});

// Create category
app.post("/category", requireAuth, async (req, res) => {
    const { name, type } = req.body;
    const username = req.user.Username;

    if (!["income", "expense"].includes(type)) {
        return res.status(400).json({ error: "Category type must be 'income' or 'expense'" });
    }

    const existing = await categories_collection.findOne({
        name: name,
        $or: [{ user: username }, { system: true }]
    });

    if (existing) {
        return res.status(409).json({ error: "Category already exists" });
    }

    const category_data = {
        name,
        type,
        user: username,
        system: false,
        created_at: new Date()
    };
    const result = await categories_collection.insertOne(category_data);

    res.json({
        message: "Category created successfully",
        id: result.insertedId.toString(),
        category: { name, type, system: false }
    });
});

// List categories
app.get("/category", requireAuth, async (req, res) => {
    const username = req.user.Username;
    let categories = await categories_collection.find({
        $or: [{ user: username }, { system: true }]
    }).toArray();

    categories = categories.map(cat => {
        return {
            ...cat,
            _id: cat._id.toString(),
            created_at: cat.created_at ? cat.created_at.toISOString() : undefined
        };
    });
    categories.sort((a, b) => (b.system ? 1 : -1) - (a.system ? 1 : -1) || a.name.localeCompare(b.name));
    res.json({ categories });
});

// Update category
app.put("/category/:name", requireAuth, async (req, res) => {
    const { name } = req.params;
    const { name: newName, type } = req.body;
    const username = req.user.Username;

    const existing = await categories_collection.findOne({
        name: name,
        user: username,
        system: false
    });

    if (!existing) {
        return res.status(404).json({ error: "Category not found or cannot be modified (system categories are read-only)" });
    }

    if (type && !["income", "expense"].includes(type)) {
        return res.status(400).json({ error: "Category type must be 'income' or 'expense'" });
    }

    let update_data = {};
    if (newName) {
        const conflict = await categories_collection.findOne({
            name: newName,
            $or: [{ user: username }, { system: true }],
            _id: { $ne: existing._id }
        });
        if (conflict) {
            return res.status(409).json({ error: "Category name already exists" });
        }
        update_data.name = newName;
    }
    if (type) update_data.type = type;
    update_data.updated_at = new Date();

    await categories_collection.updateOne(
        { name: name, user: username },
        { $set: update_data }
    );
    res.json({ message: "Category updated successfully" });
});

// Delete category
app.delete("/category/:name", requireAuth, async (req, res) => {
    const { name } = req.params;
    const username = req.user.Username;
    const result = await categories_collection.deleteOne({
        name: name,
        user: username,
        system: false
    });
    if (result.deletedCount === 0) {
        return res.status(404).json({ error: "Category not found or cannot be deleted (system categories are protected)" });
    }
    res.json({ message: "Category deleted successfully" });
});

// Category stats
app.get("/category/stats", requireAuth, async (req, res) => {
    const username = req.user.Username;
    const pipeline = [
        { $match: { $or: [{ user: username }, { system: true }] } },
        { $group: { _id: "$type", count: { $sum: 1 } } }
    ];
    const stats = await categories_collection.aggregate(pipeline).toArray();

    let formatted_stats = { income_categories: 0, expense_categories: 0, total_categories: 0 };
    for (const stat of stats) {
        if (stat._id === 'income') formatted_stats.income_categories = stat.count;
        if (stat._id === 'expense') formatted_stats.expense_categories = stat.count;
        formatted_stats.total_categories += stat.count;
    }
    res.json({ stats: formatted_stats });
});

// Admin endpoints
app.get("/admin/categories", requireAdmin, async (req, res) => {
    let categories = await categories_collection.find({}).toArray();
    categories = categories.map(cat => {
        return {
            ...cat,
            _id: cat._id.toString(),
            created_at: cat.created_at ? cat.created_at.toISOString() : undefined,
            updated_at: cat.updated_at ? cat.updated_at.toISOString() : undefined
        };
    });
    res.json({ categories });
});

app.get("/admin/categories/stats", requireAdmin, async (req, res) => {
    const total_categories = await categories_collection.countDocuments({});
    const system_categories = await categories_collection.countDocuments({ system: true });
    const user_categories = await categories_collection.countDocuments({ system: false });

    const type_pipeline = [{ $group: { _id: "$type", count: { $sum: 1 } } }];
    const type_stats = await categories_collection.aggregate(type_pipeline).toArray();

    const recent_date = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const recent_categories = await categories_collection.countDocuments({
        created_at: { $gte: recent_date },
        system: false
    });

    res.json({
        total_categories,
        system_categories,
        user_categories,
        recent_categories_7d: recent_categories,
        categories_by_type: type_stats
    });
});

// --- Mongo connection + init system cats ---
async function main() {
    const clientConn = await MongoClient.connect(MONGO_URI, { useNewUrlParser: true, useUnifiedTopology: true });
    db = clientConn.db();
    categories_collection = db.collection('categories');

    // Initialize system categories (once)
    for (const cat of SYSTEM_CATEGORIES) {
        const exists = await categories_collection.findOne({ name: cat.name, system: true });
        if (!exists) {
            await categories_collection.insertOne({ ...cat, created_at: new Date() });
        }
    }

    app.listen(PORT, () => console.log(`Category Service running on port ${PORT}`));
}

main().catch(e => {
    console.error("Failed to start service:", e);
    process.exit(1);
});
