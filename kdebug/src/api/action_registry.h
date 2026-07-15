#pragma once

#include "api/action_handler.h"
#include "api/action_spec.h"

#include <map>
#include <memory>
#include <string>
#include <vector>

namespace kdebug {

class ActionRegistry {
public:
    bool register_spec(const ActionSpec& spec);
    bool register_handler(std::unique_ptr<ActionHandler> handler);

    const ActionSpec* find_spec(const std::string& name) const;
    ActionHandler* find_handler(const std::string& name) const;

    std::vector<ActionSpec> list_specs(bool include_removed = false) const;
    Json list_descriptors(bool include_removed = false) const;

private:
    std::map<std::string, ActionSpec> specs_;
    std::map<std::string, std::unique_ptr<ActionHandler> > handlers_;
};

} // namespace kdebug

