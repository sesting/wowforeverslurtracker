local _, tracker = ...
local frame = CreateFrame("Frame")
local terms = {}
local localBoard
tracker.terms = terms
local counts
local counterCount = 0
local entries = SlurTrackerTerms or {}
if SlurTrackerTermList then
    for line in SlurTrackerTermList:gmatch("[^\n]+") do
        if line:find("%S") and not line:match("^%s*#") then
            -- Accept old three-column lists and ignore the final column.
            local id, match = line:match("^%s*([a-z0-9_]+)%s*|%s*([^|]-)%s*$")
            if not id then
                id, match = line:match("^%s*([a-z0-9_]+)%s*|%s*([^|]-)%s*|[^|]*$")
            end
            if not id or #id > 48 or (match ~= "" and entries[id]) then
                print("Slur Tracker: skipped an invalid or duplicate row in Terms.lua.")
            elseif match ~= "" then
                entries[id] = match
            end
        end
    end
end

for id, entry in pairs(entries) do
    local match = type(entry) == "table" and entry.match or entry
    if type(id) == "string" and #id <= 48 and id:match("^[a-z0-9_]+$")
        and type(match) == "string" and match:find("%S") then
        local literal = match:lower():gsub("(%W)", "%%%1")
        terms[id] = { pattern = literal, text = match }
    end
end

tracker.rulesets = {
    {"pve", "Normal (PvE)"}, {"pvp", "PvP"}, {"rp", "Roleplay"},
    {"rp-pvp", "Roleplay PvP"}, {"hardcore", "Hardcore"},
}
local rulesetLabels, empty = {}, {}
for _, rule in ipairs(tracker.rulesets) do rulesetLabels[rule[1]] = rule[2] end
tracker.rulesetLabels = rulesetLabels

function tracker.currentRuleset()
    local flags = Enum and Enum.GameRule
    if not flags or not flags.RPRuleset or not flags.PvPRuleset or not C_GameRules then return nil end
    if flags.HardcoreRuleset and C_GameRules.IsGameRuleActive(flags.HardcoreRuleset) then
        return "hardcore"
    end
    local rp = C_GameRules.IsGameRuleActive(flags.RPRuleset)
    local pvp = C_GameRules.IsGameRuleActive(flags.PvPRuleset)
    if rp then return pvp and "rp-pvp" or "rp" end
    return pvp and "pvp" or "pve"
end

local function fullName(name, surname)
    if issecretvalue and (issecretvalue(name) or issecretvalue(surname)) then return nil end
    if type(name) ~= "string" or name == "" then return nil end
    local constants = Constants and Constants.CharacterNameSeparatorConsts
    local separator = constants and constants.CHARACTERNAME_SURNAME_SEPARATOR
    if separator and separator ~= "" then
        local split = name:find(separator, 1, true)
        if split then name = name:sub(1, split-1) .. " " .. name:sub(split+#separator) end
    end
    local first, last = name:match("^([^%s%-]+)[%s%-]+([^%s]+)$")
    if not first and name:match("^[^%s%-]+$") and type(surname) == "string"
        and surname:match("^%S+$") then
        first, last = name, surname
    end
    if first and not (first .. last):find("[|:/]") then return first .. " " .. last end
end

local function decodeKey(key)
    local hex, id = key:match("^([0-9a-f]+)_(.+)$")
    if not hex or #hex % 2 ~= 0 then return nil end
    local identity = hex:gsub("%x%x", function(pair) return string.char(tonumber(pair, 16)) end)
    local ruleset, player = identity:match("^([^:]+):(.+)$")
    if rulesetLabels[ruleset] then return ruleset, player, id end
end

local dirty = false

local function flush()
    if not dirty then return true end
    local ok, sealed = pcall(SlurTrackerSeal, counts)
    if not ok or not sealed then
        print("Slur Tracker: could not seal the counters.")
        return false
    end
    SlurTrackerSealed = sealed
    dirty = false
    return true
end

local function initialize(self)
    if counts or not GetCurrentRegion or GetCurrentRegion() ~= 3 then return end
    local ok, loaded = pcall(SlurTrackerUnseal, SlurTrackerSealed)
    if not ok or not loaded then
        print("Slur Tracker: could not open the saved counters. Check the installation key.")
        return
    end
    counts = loaded
    for key in pairs(counts) do
        if decodeKey(key) then counterCount = counterCount + 1
        else
            counts[key] = nil
            dirty = true
        end
    end
    -- Prepare the first snapshot before WoW starts saving or tearing down the UI.
    dirty = dirty or SlurTrackerSealed == nil
    if not flush() then
        counts, counterCount = nil, 0
        return
    end
    self:RegisterEvent("PLAYER_LOGOUT")
    self:RegisterEvent("PLAYER_LEAVING_WORLD")
    for _, channel in ipairs({"CHANNEL", "SAY", "YELL"}) do
        self:RegisterEvent("CHAT_MSG_" .. channel)
    end
end

frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:SetScript("OnEvent", function(self, event, message, sender, _, _, _, _, _, _, _, _, _, guid)
    if event == "PLAYER_LOGIN" or event == "PLAYER_ENTERING_WORLD" then
        initialize(self)
        return
    end
    if event == "PLAYER_LOGOUT" or event == "PLAYER_LEAVING_WORLD" then
        flush()
        return
    end

    if issecretvalue and (issecretvalue(message) or issecretvalue(sender) or issecretvalue(guid)) then
        return
    end
    if type(message) ~= "string" or type(sender) ~= "string" or type(guid) ~= "string"
        or not guid:match("^Player%-") or guid == UnitGUID("player") then
        return
    end

    local text = message:lower()
    local ruleset, player = tracker.currentRuleset(), fullName(sender)
    if not ruleset or not player then return end
    local encoded = (ruleset .. ":" .. player):gsub(".", function(byte) return ("%02x"):format(byte:byte()) end)
    for id, entry in pairs(terms) do
        local _, count = text:gsub(entry.pattern, "")
        if count > 0 then
            local key = encoded .. "_" .. id
            if counts[key] then
                counts[key] = math.min(counts[key] + count, 1000000)
            elseif counterCount < 5000 then
                counts[key] = math.min(count, 1000000)
                counterCount = counterCount + 1
            end
            dirty = true
            localBoard = nil
        end
    end
end)

function tracker.playerKey()
    return fullName(UnitNameUnmodified("player"))
end

function tracker.samePlayer(left, right)
    return left and right and left:lower() == right:lower()
end

function tracker.players(shared, selected)
    if shared then
        local rows = {}
        for _, row in ipairs(SlurTrackerLeaderboard) do
            if row.ruleset == selected then rows[#rows + 1] = row end
        end
        return rows
    end
    if not localBoard then
        local grouped = {}
        for key, count in pairs(counts or {}) do
            local ruleset, name, id = decodeKey(key)
            if ruleset and terms[id] and type(count) == "number" and count > 0 then
                grouped[ruleset] = grouped[ruleset] or {}
                local players = grouped[ruleset]
                players[name] = players[name] or {player = name, terms = {}}
                players[name].terms[id] = count
            end
        end
        localBoard = {}
        for ruleset, players in pairs(grouped) do
            local rows = {}
            for _, player in pairs(players) do rows[#rows + 1] = player end
            localBoard[ruleset] = rows
        end
    end
    return localBoard[selected] or empty
end

function tracker.score(player, id)
    if id ~= "" then return player.terms[id] or 0 end
    local total = 0
    for term, count in pairs(player.terms) do
        if terms[term] then total = total + count end
    end
    return total
end

function tracker.ranking(shared, id, ruleset)
    local rows = {}
    for _, player in ipairs(tracker.players(shared, ruleset)) do
        local count = tracker.score(player, id)
        if count > 0 then rows[#rows + 1] = {player = player.player, count = count} end
    end
    table.sort(rows, function(a, b)
        if a.count ~= b.count then return a.count > b.count end
        return a.player < b.player
    end)
    local previous
    for index, row in ipairs(rows) do
        row.rank = previous and previous.count == row.count and previous.rank or index
        previous = row
    end
    return rows
end

function tracker.findPlayer(rows, name)
    for _, row in ipairs(rows) do
        if tracker.samePlayer(row.player, name) then return row end
    end
end
