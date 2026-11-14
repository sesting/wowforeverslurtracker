local band, bxor, bnot = bit.band, bit.bxor, bit.bnot
local lshift, rshift = bit.lshift, bit.rshift
local function ror(value, amount)
    return bit.bor(rshift(value, amount), lshift(value, 32-amount))
end
local char, byte = string.char, string.byte
local constants = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
}
local function word(n)
    return char(rshift(n,24), band(rshift(n,16),255), band(rshift(n,8),255), band(n,255))
end

local function sha256(message)
    local length = #message
    message = message .. "\128" .. ("\0"):rep((55-length)%64) .. word(0) .. word(length*8)
    local hash = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}
    local schedule = {}
    for offset = 1, #message, 64 do
        for index = 1, 16 do
            local a,b,c,d = byte(message, offset+4*(index-1), offset+4*index-1)
            schedule[index] = ((a*256+b)*256+c)*256+d
        end
        for index = 17, 64 do
            local x,y = schedule[index-15],schedule[index-2]
            local s0 = bxor(ror(x,7),ror(x,18),rshift(x,3))
            local s1 = bxor(ror(y,17),ror(y,19),rshift(y,10))
            schedule[index] = band(schedule[index-16]+s0+schedule[index-7]+s1,-1)
        end
        local a,b,c,d,e,f,g,h = unpack(hash)
        for index = 1, 64 do
            local s1 = bxor(ror(e,6),ror(e,11),ror(e,25))
            local choose = bxor(band(e,f),band(bnot(e),g))
            local t1 = h+s1+choose+constants[index]+schedule[index]
            local s0 = bxor(ror(a,2),ror(a,13),ror(a,22))
            local majority = bxor(band(a,b),band(a,c),band(b,c))
            h,g,f,e,d,c,b,a = g,f,e,band(d+t1,-1),c,b,a,band(t1+s0+majority,-1)
        end
        local state = {a,b,c,d,e,f,g,h}
        for index = 1, 8 do hash[index] = band(hash[index]+state[index],-1) end
    end
    for index = 1, 8 do hash[index] = word(hash[index]) end
    return table.concat(hash)
end

local function hmac(key, message)
    local padded = key .. ("\0"):rep(64-#key)
    local inner = padded:gsub(".", function(c) return char(bxor(byte(c),0x36)) end)
    local outer = padded:gsub(".", function(c) return char(bxor(byte(c),0x5c)) end)
    return sha256(outer .. sha256(inner .. message))
end

local function hex(value)
    return (value:gsub(".", function(c) return ("%02x"):format(byte(c)) end))
end

local function unhex(value)
    return (value:gsub("%x%x", function(pair) return char(tonumber(pair,16)) end))
end

local function transform(key, iv, input)
    local chunks = {}
    for offset = 1, #input, 32 do
        local mask = hmac(key, "stream\0" .. iv .. word((offset-1)/32))
        local bytes = {}
        for index = offset, math.min(offset+31,#input) do
            bytes[#bytes+1] = char(bxor(byte(input,index),byte(mask,index-offset+1)))
        end
        chunks[#chunks+1] = table.concat(bytes)
    end
    return table.concat(chunks)
end

local function keyBytes()
    local key = SlurTrackerSealKey
    if type(key) == "string" and #key == 64 and key:match("^[0-9a-f]+$") then
        return unhex(key)
    end
end

function SlurTrackerSeal(counts)
    local key = keyBytes()
    if not key then return nil end
    local rows = {}
    for id, count in pairs(counts) do
        rows[#rows+1] = ("%s=%d\n"):format(id,count)
    end
    table.sort(rows)
    local input = table.concat(rows)
    if #input > 512000 then return nil end
    local iv = hmac(key,"iv\0" .. input)
    local encrypted = transform(key,iv,input)
    local tag = hmac(key,"tag\0" .. iv .. encrypted)
    return "v1:" .. hex(iv .. tag .. encrypted)
end

function SlurTrackerUnseal(value)
    local key = keyBytes()
    if not key then return nil end
    if value == nil then return {} end
    if type(value) ~= "string" or #value < 131 or #value > 1024131 or #value%2 ~= 1
        or not value:match("^v1:[0-9a-f]+$") then return nil end
    local data = unhex(value:sub(4))
    local iv,tag,encrypted = data:sub(1,32),data:sub(33,64),data:sub(65)
    if tag ~= hmac(key,"tag\0" .. iv .. encrypted) then return nil end
    local input = transform(key,iv,encrypted)
    if iv ~= hmac(key,"iv\0" .. input) then return nil end
    local counts = {}
    local length = 0
    for id,count in input:gmatch("([0-9a-f]+_[a-z0-9_]+)=(%d+)\n") do
        length = length+#id+#count+2
        if counts[id] or #count > 7 then return nil end
        counts[id] = tonumber(count)
    end
    if length ~= #input then return nil end
    return counts
end
