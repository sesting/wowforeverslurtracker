local _, tracker = ...
local width, height = 660, 488
local pageSize = 8
local palette = {
    base = {0.055, 0.073, 0.108, 1}, panel = {0.086, 0.114, 0.159, 1},
    line = {0.20, 0.26, 0.35, 1}, accent = {0.24, 0.40, 0.56, 1},
    row = {0.105, 0.137, 0.185, 1},
    text = {0.94, 0.96, 1}, muted = {0.68, 0.75, 0.83}, gold = {1, 0.79, 0.44},
}
local frame, refresh
local state = {shared = true, tab = "board", term = "", page = 1, characterPage = 1}
local termOptions = {}
for id, entry in pairs(tracker.terms) do
    termOptions[#termOptions + 1] = {id = id, label = entry.text}
end
table.sort(termOptions, function(a, b)
    local left, right = a.label:lower(), b.label:lower()
    if left ~= right then return left < right end
    return a.id < b.id
end)
table.insert(termOptions, 1, {id = "", label = "All terms"})

local function texture(parent, color)
    local object = parent:CreateTexture(nil, "BACKGROUND")
    object:SetAllPoints()
    object:SetColorTexture(unpack(color))
    return object
end

local function place(object, parent, x, y, w, h)
    object:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
    object:SetSize(w, h)
end

local function label(parent, font, x, y, w, h, color, align)
    local object = parent:CreateFontString(nil, "OVERLAY", font)
    place(object, parent, x, y, w, h)
    object:SetJustifyH(align or "LEFT")
    object:SetWordWrap(false)
    object:SetTextColor(unpack(color or palette.text))
    return object
end

local function button(parent, caption, x, y, w, h, callback)
    local object = CreateFrame("Button", nil, parent)
    place(object, parent, x, y, w, h)
    local background = texture(object, palette.panel)
    local highlight = object:CreateTexture(nil, "HIGHLIGHT")
    highlight:SetAllPoints()
    highlight:SetColorTexture(1, 1, 1, 0.10)
    local title = label(object, "GameFontHighlight", 5, 0, w-10, h, nil, "CENTER")
    title:SetText(caption)
    object:SetScript("OnClick", callback)
    function object:mark(active)
        background:SetColorTexture(unpack(active and palette.accent or palette.panel))
    end
    function object:caption(value) title:SetText(value) end
    function object:available(value)
        self:SetEnabled(value)
        self:SetAlpha(value and 1 or 0.40)
    end
    return object
end

local function summary(prefix, entry)
    if not entry then return prefix .. "  Unranked" end
    return ("%s  #%d  ·  %d occurrences"):format(prefix, entry.rank, entry.count)
end

local function chooseTerm(id)
    state.term, state.page = id, 1
    refresh()
end

local function changeSource(shared)
    state.shared, state.page, state.characterPage = shared, 1, 1
    refresh()
end

local function createDashboard()
    frame = CreateFrame("Frame", "SlurTrackerDashboard", UIParent)
    frame:SetSize(width, height)
    frame:SetPoint("CENTER")
    frame:SetClampedToScreen(true)
    frame:SetFrameStrata("DIALOG")
    frame:EnableMouse(true)
    frame:SetMovable(true)
    texture(frame, palette.base)
    local edge = frame:CreateTexture(nil, "ARTWORK")
    edge:SetPoint("TOPLEFT")
    edge:SetPoint("TOPRIGHT")
    edge:SetHeight(3)
    edge:SetColorTexture(unpack(palette.accent))
    if UISpecialFrames then table.insert(UISpecialFrames, frame:GetName()) end

    local header = CreateFrame("Frame", nil, frame)
    place(header, frame, 18, 8, width-70, 49)
    header:EnableMouse(true)
    header:RegisterForDrag("LeftButton")
    header:SetScript("OnDragStart", function() frame:StartMoving() end)
    header:SetScript("OnDragStop", function() frame:StopMovingOrSizing() end)
    label(header, "GameFontNormalLarge", 1, 3, 255, 22, palette.gold):SetText("Slur Tracker")
    local status = label(header, "GameFontHighlightSmall", 1, 27, 540, 15, palette.muted)
    local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -8, -8)
    close:SetScript("OnClick", function() frame:Hide() end)

    local boardTab = button(frame, "Leaderboard", 18, 67, 130, 30, function()
        state.tab = "board"
        refresh()
    end)
    local characterTab = button(frame, "My character", 154, 67, 136, 30, function()
        state.tab, state.player, state.characterPage = "character", nil, 1
        state.ruleset = tracker.currentRuleset() or state.ruleset
        frame.rulesChooser:GenerateMenu()
        refresh()
    end)
    local rulesChooser = CreateFrame("DropdownButton", nil, frame, "WowStyle1DropdownTemplate")
    place(rulesChooser, frame, 299, 67, 172, 30)
    frame.rulesChooser = rulesChooser
    rulesChooser:SetupMenu(function(_, root)
        for _, rule in ipairs(tracker.rulesets) do
            root:CreateRadio(rule[2], function(id) return state.ruleset == id end, function(id)
                state.ruleset, state.page, state.characterPage = id, 1, 1
                state.tab, state.player = "board", nil
                refresh()
            end, rule[1])
        end
    end)
    local shared = button(frame, "Shared", 489, 67, 72, 30, function() changeSource(true) end)
    local observed = button(frame, "My sightings", 567, 67, 75, 30, function() changeSource(false) end)

    local content = CreateFrame("Frame", nil, frame)
    place(content, frame, 18, 110, 624, 323)
    texture(content, palette.panel)
    local board = CreateFrame("Frame", nil, content)
    board:SetAllPoints()
    local character = CreateFrame("Frame", nil, content)
    character:SetAllPoints()

    label(board, "GameFontHighlightSmall", 14, 9, 47, 30, palette.muted):SetText("Term")
    local chooser = CreateFrame("DropdownButton", nil, board, "WowStyle1DropdownTemplate")
    place(chooser, board, 60, 9, 285, 30)
    frame.chooser = chooser
    chooser:SetupMenu(function(_, root)
        root:SetScrollMode(280)
        for _, option in ipairs(termOptions) do
            root:CreateRadio(option.label, function(id) return state.term == id end, chooseTerm, option.id)
        end
    end)
    local yourRank = label(board, "GameFontHighlight", 352, 9, 256, 30, palette.gold, "RIGHT")

    local characterName = label(character, "GameFontNormalLarge", 14, 5, 375, 24, palette.gold)
    local characterInfo = label(character, "GameFontHighlightSmall", 14, 30, 395, 15, palette.muted)
    local myButton = button(character, "My character", 504, 7, 104, 29, function()
        state.player, state.characterPage = nil, 1
        state.ruleset = tracker.currentRuleset() or state.ruleset
        rulesChooser:GenerateMenu()
        refresh()
    end)
    local rankSummary = label(character, "GameFontHighlightSmall", 350, 32, 258, 15, palette.gold, "RIGHT")

    local headings = {
        label(content, "GameFontHighlightSmall", 14, 51, 64, 19, palette.muted),
        label(content, "GameFontHighlightSmall", 83, 51, 390, 19, palette.muted),
        label(content, "GameFontHighlightSmall", 472, 51, 135, 19, palette.muted, "RIGHT"),
    }
    local divider = content:CreateTexture(nil, "ARTWORK")
    place(divider, content, 12, 72, 600, 1)
    divider:SetColorTexture(unpack(palette.line))

    local rows = {}
    for index = 1, pageSize do
        local row = CreateFrame("Button", nil, content)
        place(row, content, 10, 77+(index-1)*29, 604, 27)
        row.bg = texture(row, palette.row)
        local glow = row:CreateTexture(nil, "HIGHLIGHT")
        glow:SetAllPoints()
        glow:SetColorTexture(1, 1, 1, 0.09)
        row.rank = label(row, "GameFontHighlight", 5, 0, 60, 27)
        row.name = label(row, "GameFontHighlight", 73, 0, 397, 27)
        row.count = label(row, "GameFontHighlight", 469, 0, 129, 27, nil, "RIGHT")
        row:SetScript("OnClick", function(self)
            if state.tab == "board" then
                state.player, state.tab, state.characterPage = self.value.player, "character", 1
            else
                state.term, state.tab, state.page = self.value.id, "board", 1
                chooser:GenerateMenu()
            end
            refresh()
        end)
        rows[index] = row
    end
    local empty = label(content, "GameFontHighlight", 10, 121, 604, 32, palette.muted, "CENTER")
    local helper = label(frame, "GameFontHighlightSmall", 18, 446, 356, 24, palette.muted)
    local pageLabel = label(frame, "GameFontHighlightSmall", 453, 446, 106, 24, palette.muted, "CENTER")
    local function step(delta)
        local field = state.tab == "board" and "page" or "characterPage"
        state[field] = state[field] + delta
        refresh()
    end
    local prev = button(frame, "Previous", 378, 446, 73, 24, function() step(-1) end)
    local nextPage = button(frame, "Next", 565, 446, 77, 24, function() step(1) end)
    content:EnableMouseWheel(true)
    content:SetScript("OnMouseWheel", function(_, delta)
        if (delta > 0 and prev:IsEnabled()) or (delta < 0 and nextPage:IsEnabled()) then
            step(delta > 0 and -1 or 1)
        end
    end)

    local function renderCharacter()
        local selfName = tracker.playerKey()
        local name = state.player or selfName
        local isSelf = tracker.samePlayer(name, selfName)
        local players = tracker.players(state.shared, state.ruleset)
        local data = tracker.findPlayer(players, name)
        local overall = tracker.findPlayer(tracker.ranking(state.shared, "", state.ruleset), name)
        characterName:SetText(name or "Current character")
        if isSelf then
            local class = UnitClass("player")
            local level = UnitLevel("player")
            local race = UnitRace("player")
            local info = class and level and ("Level %d  ·  %s"):format(level, class) or ""
            characterInfo:SetText(race and info ~= "" and (info .. "  ·  " .. race) or info)
        else
            characterInfo:SetText("Witnessed chat counts")
        end
        myButton:SetShown(not isSelf)
        rankSummary:SetText(summary("Overall", overall))
        local details = {}
        for _, option in ipairs(termOptions) do
            if option.id ~= "" then
                local count = data and tracker.score(data, option.id) or 0
                local rank = 1
                if count > 0 then
                    for _, player in ipairs(players) do
                        if tracker.score(player, option.id) > count then rank = rank + 1 end
                    end
                end
                details[#details + 1] = {id = option.id, label = option.label, count = count,
                                         rank = count > 0 and rank or nil}
            end
        end
        table.sort(details, function(a, b)
            if a.count ~= b.count then return a.count > b.count end
            if a.label ~= b.label then return a.label < b.label end
            return a.id < b.id
        end)
        return details
    end

    local lastLocal
    refresh = function()
        if not state.shared then lastLocal = tracker.players(false, state.ruleset) end
        local showBoard = state.tab == "board"
        local selfName = tracker.playerKey()
        local viewingSelf = not state.player or tracker.samePlayer(selfName, state.player)
        boardTab:mark(showBoard)
        characterTab:mark(not showBoard)
        characterTab:caption(not showBoard and not viewingSelf and "Character" or "My character")
        shared:mark(state.shared)
        observed:mark(not state.shared)
        board:SetShown(showBoard)
        character:SetShown(not showBoard)
        if state.shared then
            status:SetText(SlurTrackerLeaderboardUpdated
                and ("Shared snapshot  ·  " .. date("%d %b %H:%M", SlurTrackerLeaderboardUpdated))
                or "Waiting for companion sync and UI reload")
        else
            status:SetText("Public chat witnessed by this installation")
        end

        headings[1]:SetText("Rank")
        headings[2]:SetText(showBoard and "Character" or "Term")
        headings[3]:SetText("Occurrences")
        local items, field
        if showBoard then
            items, field = tracker.ranking(state.shared, state.term, state.ruleset), "page"
            if not state.shared then
                yourRank:SetText("Your own chat is excluded")
            elseif state.ruleset ~= tracker.currentRuleset() then
                yourRank:SetText("Your character is on another ruleset")
            else
                yourRank:SetText(summary("Your rank", tracker.findPlayer(items, selfName)))
            end
        else
            items, field = renderCharacter(), "characterPage"
        end
        local pages = math.max(1, math.ceil(#items / pageSize))
        state[field] = math.max(1, math.min(state[field], pages))
        local first = (state[field]-1)*pageSize
        for index, row in ipairs(rows) do
            local item = items[first+index]
            row:SetShown(item ~= nil)
            if item then
                row.value = item
                local own = showBoard and tracker.samePlayer(item.player, selfName)
                row.bg:SetColorTexture(unpack(own and palette.accent or (index%2 == 0 and palette.row or palette.panel)))
                row.rank:SetText(item.rank and ("#" .. item.rank) or "—")
                row.name:SetText(showBoard and (own and item.player .. "  (you)" or item.player) or item.label)
                row.count:SetText(tostring(item.count))
            end
        end
        empty:SetShown(#items == 0)
        empty:SetText(#termOptions == 1 and "No terms are configured." or "No scores for this filter yet.")
        helper:SetText(showBoard and "Select a character to see their term breakdown."
            or "Select a term to open its leaderboard.")
        pageLabel:SetText(("%d / %d"):format(state[field], pages))
        prev:available(state[field] > 1)
        nextPage:available(state[field] < pages)
    end

    frame:SetScript("OnShow", function()
        local scale = math.min(1, (UIParent:GetWidth()-20)/width, (UIParent:GetHeight()-20)/height)
        if scale > 0 then frame:SetScale(scale) end
        refresh()
    end)
    local elapsed = 0
    frame:SetScript("OnUpdate", function(_, delta)
        if state.shared then return end
        elapsed = elapsed + delta
        if elapsed < 1 then return end
        elapsed = 0
        if tracker.players(false, state.ruleset) ~= lastLocal then refresh() end
    end)
    frame:Hide()
end

local function openDashboard(input, shared)
    if not GetCurrentRegion or GetCurrentRegion() ~= 3 then return end
    local id = input:match("^%s*(.-)%s*$")
    if id ~= "" and not tracker.terms[id] then
        print("Slur Tracker: unknown term ID.")
        return
    end
    state.ruleset = tracker.currentRuleset()
    if not state.ruleset then
        print("Slur Tracker: the current ruleset is unavailable.")
        return
    end
    if not frame then createDashboard() end
    state.shared, state.term, state.tab, state.page = shared, id, "board", 1
    frame:Show()
    frame.chooser:GenerateMenu()
    frame.rulesChooser:GenerateMenu()
    refresh()
end

SLASH_SLURTRACKER1 = "/slurtracker"
SlashCmdList.SLURTRACKER = function(input) openDashboard(input, false) end
SLASH_SLURTRACKERSHARED1 = "/slurtrackershared"
SLASH_SLURTRACKERSHARED2 = "/st"
SlashCmdList.SLURTRACKERSHARED = function(input) openDashboard(input, true) end
