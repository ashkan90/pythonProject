-- Warrior kombo tanımlamaları
local Warrior = {
    class_name = "warrior",
    resource_type = "wp", -- Warrior Power

    -- Temel kombolar
    combos = {
        basic_attack = {
            actions = {
                {
                    keys = { "lmb" },
                    type = "press",
                    animation_time = 0.3
                },
                {
                    keys = { "rmb" },
                    type = "press",
                    animation_time = 0.4
                }
            },
            cooldown = 0.0,
            mp_cost = 0,
            range_type = "close",
            conditions = {
                check = "return true" -- Her zaman kullanılabilir
            }
        },

        ground_slash = {
            actions = {
                {
                    keys = { "shift", "rmb" },
                    type = "hold",
                    duration = 0.8,
                    animation_time = 0.5
                }
            },
            cooldown = 3.0,
            mp_cost = 15,
            range_type = "close",
            conditions = {
                check = [[
                    return game_state.wp >= 30 and
                           not game_state.character_state.value == 'stunned'
                ]]
            }
        },

        charging_slash = {
            actions = {
                {
                    keys = { "w" },
                    type = "hold",
                    duration = 0.2
                },
                {
                    keys = { "shift", "f" },
                    type = "press",
                    animation_time = 0.8
                }
            },
            cooldown = 6.0,
            mp_cost = 25,
            range_type = "mid",
            conditions = {
                check = [[
                    return game_state.wp >= 50 and
                           game_state.stamina >= 30
                ]]
            }
        },

        spinning_slash = {
            actions = {
                {
                    keys = { "shift", "q" },
                    type = "press",
                    animation_time = 0.3
                },
                {
                    keys = { "lmb" },
                    type = "hold",
                    duration = 1.2,
                    animation_time = 0.4
                }
            },
            cooldown = 8.0,
            mp_cost = 35,
            range_type = "close",
            conditions = {
                check = [[
                    return game_state.wp >= 70 and
                           not game_state.character_state.value == 'knockdown'
                ]]
            }
        },

        -- Kaçış kombosu
        emergency_escape = {
            actions = {
                {
                    keys = { "shift", "s" },
                    type = "press",
                    animation_time = 0.3
                },
                {
                    keys = { "space" },
                    type = "press",
                    animation_time = 0.5
                }
            },
            cooldown = 12.0,
            mp_cost = 10,
            range_type = "escape",
            conditions = {
                check = "return true",
            },
        },
    },
}
